# 담당: [D] | 책임: 관리자용 다중 PDF 검토·색인·게시·평가 실행.
# 구현할 기능: 제한적 검토 병렬화, HITL 승인 게이트, 순차 게시, 중단 후 재개.
# 완료 기준: 상태 파일로 완료 단계를 재사용하고 승인 전 게시하지 않는다.
from __future__ import annotations

import asyncio
import csv
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any, NoReturn

from sqlalchemy.exc import SQLAlchemyError

from starter_rag.evaluation.golden_set import _mean, _ranked_relevance_metrics
from starter_rag.ingestion.parser import extract_document_structure, parse_document
from starter_rag.ingestion.review import ReviewError, create_review, read_review, write_review
from starter_rag.progress import run_with_heartbeat
from starter_rag.storage.database import PostgresRagDatabase, database_url_from_environment
from starter_rag.storage.publication import (
    PostgresPublicationStore,
    PublicationError,
    _PublishedVersionIdentity,
)
from starter_rag.storage.vector_store import PGVectorStore


class BatchError(ValueError):
    """A batch manifest, approval, or saved state is invalid."""


def _notice(message: str) -> None:
    import sys

    print(message, file=sys.stderr, flush=True)


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".batch-", delete=False
        ) as file:
            temporary_name = file.name
            os.chmod(temporary_name, 0o600)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BatchError("일괄 검증 manifest JSON을 읽을 수 없습니다.") from None
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise BatchError("일괄 검증 manifest 버전이 올바르지 않습니다.")
    docs = data.get("documents")
    if not isinstance(docs, list) or not docs:
        raise BatchError("documents에 한 개 이상의 PDF가 필요합니다.")
    seen: set[tuple[str, str]] = set()
    for doc in docs:
        if not isinstance(doc, dict) or any(
            not isinstance(doc.get(key), str) or not doc[key].strip()
            for key in ("path", "source_id", "version", "title", "publisher", "review_file")
        ):
            raise BatchError(
                "문서마다 path, source_id, version, title, publisher, review_file이 필요합니다."
            )
        if (doc["source_id"], doc["version"]) in seen:
            raise BatchError("중복된 문서 버전입니다.")
        seen.add((doc["source_id"], doc["version"]))
        source = Path(doc["path"]).expanduser().resolve()
        if source.suffix.lower() != ".pdf" or not source.is_file():
            raise BatchError(f"PDF 원본을 확인하세요: {doc['source_id']}")
        doc["path"] = str(source)
        doc["review_file"] = str(Path(doc["review_file"]).expanduser().resolve())
    collection = data.get("collection_id", "published-guides")
    if not isinstance(collection, str) or not collection.strip():
        raise BatchError("collection_id가 필요합니다.")
    data["collection_id"] = collection
    return data


def _state(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    fingerprint = sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if not path.exists():
        return {
            "schema_version": 2,
            "manifest_sha256": fingerprint,
            "documents": {},
            "evaluation": "not_started",
        }
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BatchError("일괄 검증 상태 파일을 읽을 수 없습니다.") from None
    if not isinstance(saved, dict) or saved.get("manifest_sha256") != fingerprint:
        raise BatchError("manifest가 이전 실행과 다릅니다. 별도 상태 파일을 사용하세요.")
    documents = saved.get("documents")
    if not isinstance(documents, dict):
        raise BatchError("일괄 검증 상태의 documents 형식이 올바르지 않습니다.")

    manifest_documents = manifest["documents"]
    expected_keys = {
        _document_state_key(doc["source_id"], doc["version"]): doc for doc in manifest_documents
    }
    if saved.get("schema_version") == 1:
        matching_documents: dict[str, list[dict[str, str]]] = {}
        for doc in manifest_documents:
            matching_documents.setdefault(doc["source_id"], []).append(doc)
        migrated: dict[str, Any] = {}
        for source_id, entry in documents.items():
            matches = matching_documents.get(source_id, [])
            if len(matches) != 1 or not isinstance(entry, dict):
                raise BatchError(
                    "이전 상태 파일에서 Source ID와 버전을 안전하게 구분할 수 없습니다. "
                    "기존 파일을 보존하고 별도 상태 파일로 시작하세요."
                )
            doc = matches[0]
            migrated[_document_state_key(source_id, doc["version"])] = entry
        saved = {**saved, "schema_version": 2, "documents": migrated}
        documents = migrated
    elif saved.get("schema_version") != 2:
        raise BatchError("지원하지 않는 일괄 검증 상태 파일 버전입니다.")

    if set(documents) - set(expected_keys):
        raise BatchError("상태 파일에 현재 manifest에 없는 문서 항목이 있습니다.")
    allowed_statuses = {"failed", "approval_pending", "indexed", "published"}
    if any(
        not isinstance(entry, dict)
        or (
            "status" in entry
            and (not isinstance(entry["status"], str) or entry["status"] not in allowed_statuses)
        )
        for entry in documents.values()
    ):
        raise BatchError("일괄 검증 상태의 문서 항목을 안전하게 해석할 수 없습니다.")
    return saved


def _document_state_key(source_id: str, version: str) -> str:
    return json.dumps((source_id, version), ensure_ascii=False, separators=(",", ":"))


def _has_trusted_chunk_count(value: object) -> bool:
    return type(value) is int and value > 0


def _published_version_identity(
    source_id: str, version: str, collection_id: str
) -> _PublishedVersionIdentity | None:
    """Read the published source and approval fingerprints without changing the DB."""
    return _read_publication_store(
        collection_id,
        lambda store: store._published_version_identity(source_id, version),
    )


def _gold_ids_present(ids: set[str], collection_id: str) -> set[str]:
    return _read_vector_store(
        collection_id,
        lambda store: store._published_chunk_ids(sorted(ids)),
    )


def _read_publication_store[ResultT](
    collection_id: str,
    query: Callable[[PostgresPublicationStore], Awaitable[ResultT]],
) -> ResultT:
    return _read_storage_store(
        lambda database: PostgresPublicationStore(database, collection_id=collection_id),
        query,
    )


def _read_vector_store[ResultT](
    collection_id: str,
    query: Callable[[PGVectorStore], Awaitable[ResultT]],
) -> ResultT:
    return _read_storage_store(
        lambda database: PGVectorStore(database, collection_id=collection_id),
        query,
    )


def _read_storage_store[StoreT, ResultT](
    store_factory: Callable[[PostgresRagDatabase], StoreT],
    query: Callable[[StoreT], Awaitable[ResultT]],
) -> ResultT:
    async def read() -> ResultT:
        database = PostgresRagDatabase(database_url_from_environment())
        try:
            return await query(store_factory(database))
        except SQLAlchemyError:
            raise BatchError("로컬 DB 조회 실패: 연결과 초기화 상태를 확인하세요.") from None
        finally:
            await database.close()

    return asyncio.run(read())


def _prepare_one(doc: dict[str, str]) -> tuple[str, str]:
    source = Path(doc["path"])
    review_path = Path(doc["review_file"])
    if review_path.exists():
        read_review(review_path, source=source, source_id=doc["source_id"], version=doc["version"])
        return doc["source_id"], "reused_review"
    document = run_with_heartbeat(
        lambda: parse_document(source),
        f"PDF 파싱 {doc['source_id']}",
        enabled=True,
    )
    structure = extract_document_structure(document, source)
    pages = getattr(document, "pages", None)
    try:
        page_count = len(pages) if pages is not None else 0
    except TypeError:
        page_count = 0
    if page_count:
        _notice(f"PDF 파싱: {page_count}/{page_count}페이지 완료 ({doc['source_id']})")
    review = create_review(source, structure, source_id=doc["source_id"], version=doc["version"])
    write_review(review_path, review)
    return doc["source_id"], "prepared"


def _capture_cli(
    arguments: list[str], *, progress: bool = False
) -> tuple[int, dict[str, Any] | None]:
    from starter_rag.cli import main

    output = StringIO()
    previous_progress = os.environ.get("RAG_PROGRESS")
    if progress:
        os.environ["RAG_PROGRESS"] = "1"
    try:
        with redirect_stdout(output):
            code = main(arguments)
    finally:
        if progress:
            if previous_progress is None:
                os.environ.pop("RAG_PROGRESS", None)
            else:
                os.environ["RAG_PROGRESS"] = previous_progress
    if code:
        return code, None
    try:
        return 0, json.loads(output.getvalue())
    except ValueError:
        raise BatchError("CLI 결과 JSON이 올바르지 않습니다.") from None


def run_batch(
    manifest_path: Path,
    state_path: Path,
    *,
    phase: str,
    prepare_workers: int = 2,
    evaluation_output_path: Path | None = None,
) -> int:
    if phase not in {"all", "prepare", "load", "evaluate"} or prepare_workers not in {1, 2}:
        raise BatchError("phase 또는 prepare_workers가 올바르지 않습니다.")
    database_url_from_environment()  # Batch operations are restricted to the selected local DB.
    manifest = _manifest(manifest_path)
    state = _state(state_path, manifest)
    documents = manifest["documents"]
    for doc in documents:
        state_key = _document_state_key(doc["source_id"], doc["version"])
        entry = state["documents"].setdefault(state_key, {})
        try:
            published = _published_version_identity(
                doc["source_id"], doc["version"], manifest["collection_id"]
            )
        except (BatchError, PublicationError) as exc:
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                type(exc).__name__,
            )
        if published is None:
            if entry.get("status") == "published":
                _fail_published_reuse(
                    state_path,
                    state,
                    entry,
                    doc["source_id"],
                    "PublishedRecordMissing",
                )
            continue
        expected_chunk_count = entry.get("chunk_count")
        if not _has_trusted_chunk_count(expected_chunk_count):
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                "ExpectedChunkCountUnavailable",
            )
        if published.chunk_count != expected_chunk_count:
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                "PublishedChunkCountMismatch",
            )

        try:
            report, _ = read_review(
                Path(doc["review_file"]),
                require_approved=True,
                source=Path(doc["path"]),
                source_id=doc["source_id"],
                version=doc["version"],
            )
        except (ReviewError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                type(exc).__name__,
            )

        source_sha256 = report["source"]["sha256"]
        review_sha256 = report["approval"]["content_sha256"]
        if (
            not source_sha256
            or not review_sha256
            or published.content_sha256 != source_sha256
            or published.review_sha256 != review_sha256
            or entry.get("source_sha256", source_sha256) != source_sha256
            or entry.get("review_sha256", review_sha256) != review_sha256
        ):
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                "PublishedFingerprintMismatch",
            )
        if (
            published.source_title != doc["title"]
            or published.publisher != doc["publisher"]
            or published.source_url != (doc.get("source_url") or None)
        ):
            _fail_published_reuse(
                state_path,
                state,
                entry,
                doc["source_id"],
                "PublishedMetadataMismatch",
            )
        entry.update(
            status="published",
            chunk_count=published.chunk_count,
            source_sha256=source_sha256,
            review_sha256=review_sha256,
        )
    _atomic_json(state_path, state)
    if phase in {"all", "prepare"}:
        pending = [
            doc
            for doc in documents
            if state["documents"]
            .get(_document_state_key(doc["source_id"], doc["version"]), {})
            .get("status")
            != "published"
        ]
        with ThreadPoolExecutor(max_workers=prepare_workers) as pool:
            futures = {pool.submit(_prepare_one, doc): doc for doc in pending}
            for future in as_completed(futures):
                doc = futures[future]
                try:
                    source_id, status = future.result()
                except Exception as exc:  # noqa: BLE001 - persist the failed stage before returning.
                    state["documents"][_document_state_key(doc["source_id"], doc["version"])] = {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                    }
                    _atomic_json(state_path, state)
                    raise BatchError(
                        f"{doc['source_id']} 검토 파일 준비 실패: {type(exc).__name__}"
                    ) from None
                state["documents"].setdefault(_document_state_key(source_id, doc["version"]), {})[
                    "status"
                ] = "approval_pending"
                _atomic_json(state_path, state)
                _notice(
                    f"검토 파일: {len([x for x in state['documents'].values() if x.get('status') == 'approval_pending'])}/{len(pending)}건 완료 ({source_id}, {status})"
                )
    if phase == "prepare":
        return 0
    if phase in {"all", "load"}:
        for number, doc in enumerate(documents, 1):
            source_id = doc["source_id"]
            entry = state["documents"].setdefault(
                _document_state_key(source_id, doc["version"]), {}
            )
            if entry.get("status") == "published":
                _notice(f"게시: {number}/{len(documents)}건 확인 ({source_id}, 기존 완료 재사용)")
                continue
            try:
                report, _ = read_review(
                    Path(doc["review_file"]),
                    require_approved=True,
                    source=Path(doc["path"]),
                    source_id=source_id,
                    version=doc["version"],
                )
            except (ReviewError, OSError):
                entry["status"] = "approval_pending"
                _atomic_json(state_path, state)
                _notice(f"{source_id}: 사용자 HITL 승인이 필요합니다: {doc['review_file']}")
                return 3
            if entry.get("status") == "indexed" and not _has_trusted_chunk_count(
                entry.get("chunk_count")
            ):
                entry.update(
                    status="failed",
                    stage="verify_indexed",
                    error_type="ExpectedChunkCountUnavailable",
                )
                _atomic_json(state_path, state)
                raise BatchError(
                    f"{source_id}: 색인 예상 청크 수를 확인할 수 없어 게시를 중단했습니다."
                )
            if entry.get("status") != "indexed":
                arguments = [
                    "index",
                    doc["path"],
                    "--source-id",
                    source_id,
                    "--version",
                    doc["version"],
                    "--source-title",
                    doc["title"],
                    "--publisher",
                    doc["publisher"],
                    "--collection-id",
                    manifest["collection_id"],
                    "--review-file",
                    doc["review_file"],
                ]
                if doc.get("source_url"):
                    arguments += ["--source-url", doc["source_url"]]
                code, result = _capture_cli(arguments, progress=True)
                if code:
                    entry.update(status="failed", stage="index", exit_code=code)
                    _atomic_json(state_path, state)
                    return code
                chunk_count = result.get("chunkCount") if isinstance(result, dict) else None
                if not _has_trusted_chunk_count(chunk_count):
                    entry.update(
                        status="failed",
                        stage="index",
                        error_type="ExpectedChunkCountUnavailable",
                    )
                    _atomic_json(state_path, state)
                    raise BatchError(
                        f"{source_id}: 색인 결과에서 신뢰할 수 있는 청크 수를 확인할 수 없습니다."
                    )
                entry.update(
                    status="indexed",
                    chunk_count=chunk_count,
                    source_sha256=report["source"]["sha256"],
                    review_sha256=report["approval"]["content_sha256"],
                )
                _atomic_json(state_path, state)
            code, _ = _capture_cli(
                [
                    "publish",
                    "--source-id",
                    source_id,
                    "--version",
                    doc["version"],
                    "--collection-id",
                    manifest["collection_id"],
                    "--review-file",
                    doc["review_file"],
                ],
                progress=True,
            )
            if code:
                entry.update(status="failed", stage="publish", exit_code=code)
                _atomic_json(state_path, state)
                return code
            entry["status"] = "published"
            _atomic_json(state_path, state)
            _notice(f"게시: {number}/{len(documents)}건 완료 ({source_id})")
    if phase in {"all", "evaluate"}:
        evaluation = manifest.get("evaluation")
        if evaluation:
            try:
                report = evaluate_cases(
                    Path(evaluation["cases"]),
                    Path(evaluation["gold"]),
                    manifest["collection_id"],
                )
            except Exception as exc:  # noqa: BLE001 - save failed evaluation state before returning.
                state["evaluation"] = "failed"
                state["evaluation_error_type"] = type(exc).__name__
                _atomic_json(state_path, state)
                raise BatchError(f"검색 평가 실패: {type(exc).__name__}") from None
            if evaluation_output_path is not None:
                _atomic_json(evaluation_output_path, report)
            state["evaluation"] = report["status"]
            state.pop("evaluation_error_type", None)
            _atomic_json(state_path, state)
            print(
                json.dumps(
                    {
                        "success": state["evaluation"] == "complete",
                        "report": (
                            str(evaluation_output_path)
                            if evaluation_output_path is not None
                            else None
                        ),
                        "documentMetrics": report["document_metrics"],
                        "evidenceMetrics": report["evidence_metrics"],
                    },
                    ensure_ascii=False,
                )
            )
            return (
                0
                if state["evaluation"] == "complete"
                else (3 if state["evaluation"] == "gold_ids_unmapped" else 1)
            )
    print(
        json.dumps(
            {"success": True, "state": str(state_path), "documents": state["documents"]},
            ensure_ascii=False,
        )
    )
    return 0


def _fail_published_reuse(
    state_path: Path,
    state: dict[str, Any],
    entry: dict[str, Any],
    source_id: str,
    error_type: str,
) -> NoReturn:
    entry.update(status="failed", stage="verify_published", error_type=error_type)
    _atomic_json(state_path, state)
    raise BatchError(
        f"{source_id}: 기존 게시 결과와 현재 원본/HITL 승인 정보를 확인할 수 없습니다."
    )


def evaluate_cases(cases_path: Path, gold_path: Path, collection_id: str) -> dict[str, Any]:
    """Search approved questions; score IDs only if every approved ID exists in the corpus."""
    from starter_rag.cli import main

    with cases_path.open(encoding="utf-8-sig", newline="") as file:
        cases = list(csv.DictReader(file))
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    approved = {item["query_id"]: item for item in gold["queries"] if item.get("gold_evidence_ids")}
    if not cases or len(cases) != len(approved) or set(approved) != {case["id"] for case in cases}:
        raise BatchError("평가 질문과 승인된 정답 항목이 일치하지 않습니다.")
    all_gold_ids = {
        evidence_id for query in approved.values() for evidence_id in query["gold_evidence_ids"]
    }
    present = _gold_ids_present(all_gold_ids, collection_id)
    gold_mapped = present == all_gold_ids
    rows: list[dict[str, Any]] = []
    for number, case in enumerate(cases, 1):
        if approved[case["id"]]["question"] != case["question"]:
            raise BatchError(f"질문 원문이 다릅니다: {case['id']}")
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                ["search", case["question"], "--top-k", "10", "--collection-id", collection_id]
            )
        if code:
            rows.append({"id": case["id"], "status": "failed", "exit_code": code})
        else:
            result = json.loads(output.getvalue())
            found = [item["evidence_id"] for item in result["evidence"]]
            found_sources = [item["source"]["source_id"] for item in result["evidence"]]
            wanted = set(approved[case["id"]]["gold_evidence_ids"])
            expected_source = approved[case["id"]]["expected_source_id"]
            evidence_indexes = {
                evidence_id: index for index, evidence_id in enumerate(sorted(wanted))
            }
            evidence_matches = [
                {evidence_indexes[evidence_id]} if evidence_id in evidence_indexes else set()
                for evidence_id in found
            ]
            evidence_metrics = _ranked_relevance_metrics(
                evidence_matches, len(evidence_indexes), (3, 5, 10)
            )
            document_matches = [
                {0} if source_id == expected_source else set() for source_id in found_sources
            ]
            document_metrics = _ranked_relevance_metrics(document_matches, 1, (3, 5, 10))
            row = {
                "id": case["id"],
                "status": "ok",
                "returned_evidence_ids": found,
                "returned_sources": found_sources,
                "document_hit_at_3": int(document_metrics[3]["recall"]),
                "document_hit_at_5": int(document_metrics[5]["recall"]),
                "document_hit_at_10": int(document_metrics[10]["recall"]),
                "document_mrr_at_10": document_metrics[10]["mrr"],
                **(
                    {
                        "recall_at_3": evidence_metrics[3]["recall"],
                        "recall_at_5": evidence_metrics[5]["recall"],
                        "recall_at_10": evidence_metrics[10]["recall"],
                        "mrr_at_10": evidence_metrics[10]["mrr"],
                        "full_evidence_coverage_at_10": int(evidence_metrics[10]["complete"]),
                    }
                    if gold_mapped
                    else {}
                ),
            }
            rows.append(row)
        _notice(f"검색 평가: {number}/{len(cases)}문항 완료 ({case['id']}, {rows[-1]['status']})")
    completed = [row for row in rows if row["status"] == "ok"]
    metric_names = (
        "recall_at_3",
        "recall_at_5",
        "recall_at_10",
        "mrr_at_10",
        "full_evidence_coverage_at_10",
    )
    metrics = {
        key: _mean([row[key] for row in completed]) if completed and gold_mapped else None
        for key in metric_names
    }
    document_metrics = {
        key: _mean([row[key] for row in completed]) if completed else None
        for key in (
            "document_hit_at_3",
            "document_hit_at_5",
            "document_hit_at_10",
            "document_mrr_at_10",
        )
    }
    return {
        "status": "complete"
        if len(completed) == len(cases) and gold_mapped
        else "gold_ids_unmapped"
        if not gold_mapped
        else "failed",
        "total": len(cases),
        "completed": len(completed),
        "gold_evidence_count": len(all_gold_ids),
        "excluded_questions": sorted(
            {item["query_id"] for item in gold["queries"]} - set(approved)
        ),
        "missing_gold_evidence_ids": sorted(all_gold_ids - present),
        "document_metrics": document_metrics,
        "evidence_metrics": metrics,
        "warning": "Evidence ID 변경 시 원문 위치를 대조해 승인 정답을 재매핑해야 합니다. 답변 품질이나 정책 준수는 측정하지 않습니다.",
        "cases": rows,
    }
