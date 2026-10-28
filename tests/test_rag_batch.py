"""Batch approval gates, sequential publication, and resume state."""

from __future__ import annotations

import asyncio
import json
import os
from hashlib import sha256
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import OperationalError
from starter_rag import batch
from starter_rag import cli as rag_cli
from starter_rag.ingestion.review import ReviewError


def _files(directory: Path) -> tuple[Path, Path, Path]:
    pdfs = []
    documents = []
    for index in (1, 2):
        pdf = directory / f"source-{index}.pdf"
        pdf.write_bytes(b"%PDF-1.4 test only")
        pdfs.append(pdf)
        documents.append(
            {
                "path": str(pdf),
                "source_id": f"source-{index}",
                "version": "v1",
                "title": f"Guide {index}",
                "publisher": "Publisher",
                "review_file": str(directory / f"review-{index}.json"),
            }
        )
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "collection_id": "isolated", "documents": documents}),
        encoding="utf-8",
    )
    return manifest, directory / "state.json", pdfs[0]


def _source_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _review_sha256(source_id: str, version: str) -> str:
    return sha256(f"approval:{source_id}:{version}".encode()).hexdigest()


def _published_identity(doc: dict[str, str]) -> batch._PublishedVersionIdentity:
    return batch._PublishedVersionIdentity(
        chunk_count=2,
        content_sha256=_source_sha256(Path(doc["path"])),
        review_sha256=_review_sha256(doc["source_id"], doc["version"]),
        source_title=doc["title"],
        publisher=doc["publisher"],
        source_url=doc.get("source_url") or None,
    )


def _published_for_manifest(manifest: Path) -> list[batch._PublishedVersionIdentity]:
    return [_published_identity(doc) for doc in batch._manifest(manifest)["documents"]]


def _approved_review(_path: Path, **kwargs):
    source = Path(kwargs["source"])
    source_id = kwargs["source_id"]
    version = kwargs["version"]
    return (
        {
            "source": {"sha256": _source_sha256(source)},
            "approval": {"content_sha256": _review_sha256(source_id, version)},
        },
        object(),
    )


def _save_state_entry(
    manifest_path: Path,
    state_path: Path,
    doc: dict[str, str],
    entry: dict[str, object],
) -> None:
    saved = batch._state(state_path, batch._manifest(manifest_path))
    saved["documents"][batch._document_state_key(doc["source_id"], doc["version"])] = entry
    state_path.write_text(json.dumps(saved), encoding="utf-8")


def test_승인_전에는_색인을_멈추고_재개_상태를_기록한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_prepare_one", side_effect=lambda doc: (doc["source_id"], "prepared")),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(batch, "read_review", side_effect=ReviewError("approval needed")),
        patch.object(batch, "_capture_cli") as cli,
    ):
        assert batch.run_batch(manifest, state, phase="all") == 3
        cli.assert_not_called()
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["documents"][batch._document_state_key("source-1", "v1")]["status"] == (
        "approval_pending"
    )
    assert saved["documents"][batch._document_state_key("source-2", "v1")]["status"] == (
        "approval_pending"
    )


def test_승인된_문서를_순차_색인_게시하고_완료_상태를_재사용한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    calls = []

    def capture(args, *, progress=False):
        assert progress is True
        calls.append((args[0], args[args.index("--source-id") + 1]))
        return 0, {"chunkCount": 2} if args[0] == "index" else {"success": True}

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_prepare_one", side_effect=lambda doc: (doc["source_id"], "prepared")),
        patch.object(
            batch,
            "_published_version_identity",
            side_effect=[None, None, *_published_for_manifest(manifest)],
        ),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli", side_effect=capture),
    ):
        assert batch.run_batch(manifest, state, phase="all") == 0
        assert batch.run_batch(manifest, state, phase="all") == 0
    assert calls == [
        ("index", "source-1"),
        ("publish", "source-1"),
        ("index", "source-2"),
        ("publish", "source-2"),
    ]
    assert all(
        value["status"] == "published"
        for value in json.loads(state.read_text(encoding="utf-8"))["documents"].values()
    )


def test_게시_청크_수가_최초_색인_예상과_다르면_재사용하지_않는다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    doc = batch._manifest(manifest)["documents"][0]
    identity = _published_identity(doc)
    _save_state_entry(
        manifest,
        state,
        doc,
        {"status": "published", "chunk_count": 3},
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=identity),
        patch.object(batch, "read_review") as review,
        patch.object(batch, "_capture_cli") as cli,
    ):
        try:
            batch.run_batch(manifest, state, phase="load")
        except batch.BatchError:
            pass
        else:
            raise AssertionError("게시 청크 수가 색인 예상과 다른 자료를 재사용했습니다.")

    entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
        batch._document_state_key("source-1", "v1")
    ]
    assert entry["status"] == "failed"
    assert entry["error_type"] == "PublishedChunkCountMismatch"
    review.assert_not_called()
    cli.assert_not_called()


def test_예상_청크_수가_없거나_신뢰할_수_없으면_게시결과를_재사용하지_않는다(
    tmp_path: Path,
) -> None:
    for index, invalid_count in enumerate((None, 0, True, "2")):
        case_path = tmp_path / str(index)
        case_path.mkdir()
        manifest, state, _ = _files(case_path)
        doc = batch._manifest(manifest)["documents"][0]
        _save_state_entry(
            manifest,
            state,
            doc,
            {"status": "published", "chunk_count": invalid_count},
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                    "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
                },
            ),
            patch.object(
                batch, "_published_version_identity", return_value=_published_identity(doc)
            ),
            patch.object(batch, "read_review") as review,
            patch.object(batch, "_capture_cli") as cli,
        ):
            try:
                batch.run_batch(manifest, state, phase="load")
            except batch.BatchError:
                pass
            else:
                raise AssertionError("신뢰할 수 없는 청크 예상 수로 게시 자료를 재사용했습니다.")

        entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
            batch._document_state_key("source-1", "v1")
        ]
        assert entry["status"] == "failed"
        assert entry["error_type"] == "ExpectedChunkCountUnavailable"
        review.assert_not_called()
        cli.assert_not_called()


def test_게시_출처_메타데이터가_현재_manifest와_다르면_재사용하지_않는다(
    tmp_path: Path,
) -> None:
    changes = {
        "title": "Updated guide title",
        "publisher": "Updated publisher",
        "source_url": "https://example.invalid/updated",
    }
    for index, (field, changed_value) in enumerate(changes.items()):
        case_path = tmp_path / str(index)
        case_path.mkdir()
        manifest, state, _ = _files(case_path)
        old_doc = batch._manifest(manifest)["documents"][0]
        identity = _published_identity(old_doc)
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_data["documents"][0][field] = changed_value
        manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
        current_doc = batch._manifest(manifest)["documents"][0]
        _save_state_entry(
            manifest,
            state,
            current_doc,
            {
                "status": "published",
                "chunk_count": identity.chunk_count,
                "source_sha256": identity.content_sha256,
                "review_sha256": identity.review_sha256,
            },
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                    "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
                },
            ),
            patch.object(batch, "_published_version_identity", return_value=identity),
            patch.object(batch, "read_review", side_effect=_approved_review),
            patch.object(batch, "_prepare_one") as prepare,
            patch.object(batch, "_capture_cli") as cli,
        ):
            try:
                batch.run_batch(manifest, state, phase="load")
            except batch.BatchError:
                pass
            else:
                raise AssertionError(f"{field}가 변경된 게시 자료를 재사용했습니다.")

        entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
            batch._document_state_key("source-1", "v1")
        ]
        assert entry["status"] == "failed"
        assert entry["error_type"] == "PublishedMetadataMismatch"
        prepare.assert_not_called()
        cli.assert_not_called()


def test_색인_예상_청크_수를_확인할_수_없으면_게시하지_않는다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    calls = []

    def capture(arguments, *, progress=False):
        calls.append(arguments[0])
        return 0, {"chunkCount": None}

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(batch, "_prepare_one", side_effect=lambda doc: (doc["source_id"], "prepared")),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli", side_effect=capture),
    ):
        try:
            batch.run_batch(manifest, state, phase="all")
        except batch.BatchError:
            pass
        else:
            raise AssertionError("예상 청크 수가 없는 색인 결과를 게시했습니다.")

    entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
        batch._document_state_key("source-1", "v1")
    ]
    assert entry["status"] == "failed"
    assert entry["stage"] == "index"
    assert entry["error_type"] == "ExpectedChunkCountUnavailable"
    assert calls == ["index"]


def test_변경된_PDF는_기존_게시결과와_해시가_달라_재사용하지_않는다(tmp_path: Path) -> None:
    manifest, state, first_pdf = _files(tmp_path)
    manifest_data = batch._manifest(manifest)
    document = manifest_data["documents"][0]
    old_source_hash = _source_sha256(first_pdf)
    old_review_hash = _review_sha256(document["source_id"], document["version"])
    manifest_hash = sha256(
        json.dumps(manifest_data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    state.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "manifest_sha256": manifest_hash,
                "documents": {
                    batch._document_state_key("source-1", "v1"): {
                        "status": "published",
                        "chunk_count": 2,
                        "source_sha256": old_source_hash,
                        "review_sha256": old_review_hash,
                    }
                },
                "evaluation": "not_started",
            }
        ),
        encoding="utf-8",
    )
    first_pdf.write_bytes(b"%PDF-1.4 changed source")
    current_source_hash = _source_sha256(first_pdf)
    old_identity = batch._PublishedVersionIdentity(
        chunk_count=2,
        content_sha256=old_source_hash,
        review_sha256=old_review_hash,
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=old_identity),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_prepare_one") as prepare,
        patch.object(batch, "_capture_cli") as cli,
    ):
        try:
            batch.run_batch(manifest, state, phase="all")
        except batch.BatchError as exc:
            assert "현재 원본/HITL 승인 정보" in str(exc)
        else:
            raise AssertionError("변경된 PDF에 이전 게시 결과를 재사용했습니다.")

    saved = json.loads(state.read_text(encoding="utf-8"))
    entry = saved["documents"][batch._document_state_key("source-1", "v1")]
    assert entry["status"] == "failed"
    assert entry["stage"] == "verify_published"
    assert entry["error_type"] == "PublishedFingerprintMismatch"
    assert current_source_hash != old_identity.content_sha256
    prepare.assert_not_called()
    cli.assert_not_called()


def test_DB에_원본_해시가_없으면_게시결과를_재사용하지_않는다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    document = batch._manifest(manifest)["documents"][0]
    identity = batch._PublishedVersionIdentity(
        chunk_count=2,
        content_sha256=None,
        review_sha256=_review_sha256(document["source_id"], document["version"]),
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=identity),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli") as cli,
    ):
        try:
            batch.run_batch(manifest, state, phase="load")
        except batch.BatchError:
            pass
        else:
            raise AssertionError("DB 출처 해시가 없는 게시 결과를 재사용했습니다.")

    entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
        batch._document_state_key("source-1", "v1")
    ]
    assert entry["status"] == "failed"
    assert entry["stage"] == "verify_published"
    cli.assert_not_called()


def test_DB에_HITL_승인_해시가_없으면_게시결과를_재사용하지_않는다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    document = batch._manifest(manifest)["documents"][0]
    identity = batch._PublishedVersionIdentity(
        chunk_count=2,
        content_sha256=_source_sha256(Path(document["path"])),
        review_sha256=None,
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=identity),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli") as cli,
    ):
        try:
            batch.run_batch(manifest, state, phase="load")
        except batch.BatchError:
            pass
        else:
            raise AssertionError("DB HITL 승인 해시가 없는 게시 결과를 재사용했습니다.")

    entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
        batch._document_state_key("source-1", "v1")
    ]
    assert entry["status"] == "failed"
    assert entry["stage"] == "verify_published"
    cli.assert_not_called()


def test_승인_해시가_DB와_다르면_게시결과를_재사용하지_않는다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    document = batch._manifest(manifest)["documents"][0]
    identity = _published_identity(document)
    identity = batch._PublishedVersionIdentity(
        chunk_count=identity.chunk_count,
        content_sha256=identity.content_sha256,
        review_sha256="stale-approval-hash",
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_published_version_identity", return_value=identity),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli") as cli,
    ):
        try:
            batch.run_batch(manifest, state, phase="load")
        except batch.BatchError:
            pass
        else:
            raise AssertionError("DB 승인 해시가 다른 게시 결과를 재사용했습니다.")

    entry = json.loads(state.read_text(encoding="utf-8"))["documents"][
        batch._document_state_key("source-1", "v1")
    ]
    assert entry["status"] == "failed"
    assert entry["stage"] == "verify_published"
    cli.assert_not_called()


def test_같은_Source_ID의_서로_다른_버전을_독립적으로_게시하고_재사용한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["documents"][1]["source_id"] = "source-1"
    manifest_data["documents"][1]["version"] = "v2"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    calls = []

    def capture(args, *, progress=False):
        version = args[args.index("--version") + 1]
        calls.append((args[0], version))
        return 0, {"chunkCount": 2} if args[0] == "index" else {"success": True}

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_prepare_one", side_effect=lambda doc: (doc["source_id"], "prepared")),
        patch.object(
            batch,
            "_published_version_identity",
            side_effect=[None, None, *_published_for_manifest(manifest)],
        ),
        patch.object(
            batch,
            "read_review",
            side_effect=_approved_review,
        ),
        patch.object(batch, "_capture_cli", side_effect=capture),
    ):
        assert batch.run_batch(manifest, state, phase="all") == 0
        assert batch.run_batch(manifest, state, phase="all") == 0

    assert calls == [("index", "v1"), ("publish", "v1"), ("index", "v2"), ("publish", "v2")]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert saved["documents"][batch._document_state_key("source-1", "v1")]["status"] == (
        "published"
    )
    assert saved["documents"][batch._document_state_key("source-1", "v2")]["status"] == (
        "published"
    )


def test_여러_버전_중_부분_실패를_버전별로_저장하고_재개한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["documents"][1]["source_id"] = "source-1"
    manifest_data["documents"][1]["version"] = "v2"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    published_doc = batch._manifest(manifest)["documents"][0]
    published_identity = _published_identity(published_doc)
    _save_state_entry(
        manifest,
        state,
        published_doc,
        {
            "status": "published",
            "chunk_count": published_identity.chunk_count,
            "source_sha256": published_identity.content_sha256,
            "review_sha256": published_identity.review_sha256,
        },
    )
    calls = []

    def capture(args, *, progress=False):
        version = args[args.index("--version") + 1]
        calls.append((args[0], version))
        if (args[0], version) == ("index", "v2") and calls.count(("index", "v2")) == 1:
            return 1, None
        return 0, {"chunkCount": 2} if args[0] == "index" else {"success": True}

    with (
        patch.dict(
            "os.environ",
            {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/starter_rag_integration",
                "RAG_LOCAL_DATABASE_NAME": "starter_rag_integration",
            },
        ),
        patch.object(batch, "_prepare_one", side_effect=lambda doc: (doc["source_id"], "prepared")),
        patch.object(
            batch,
            "_published_version_identity",
            side_effect=[
                published_identity,
                None,
                published_identity,
                None,
            ],
        ),
        patch.object(batch, "read_review", side_effect=_approved_review),
        patch.object(batch, "_capture_cli", side_effect=capture),
    ):
        assert batch.run_batch(manifest, state, phase="all") == 1
        failed = json.loads(state.read_text(encoding="utf-8"))
        assert failed["documents"][batch._document_state_key("source-1", "v1")]["status"] == (
            "published"
        )
        assert failed["documents"][batch._document_state_key("source-1", "v2")] == {
            "status": "failed",
            "stage": "index",
            "exit_code": 1,
        }
        assert batch.run_batch(manifest, state, phase="all") == 0

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["documents"][batch._document_state_key("source-1", "v1")]["status"] == (
        "published"
    )
    assert saved["documents"][batch._document_state_key("source-1", "v2")]["status"] == (
        "published"
    )


def test_기존_단일_버전_상태는_안전하게_새_키로_이관한다(tmp_path: Path) -> None:
    manifest_path, state_path, _ = _files(tmp_path)
    manifest = batch._manifest(manifest_path)
    fingerprint = batch.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_sha256": fingerprint,
                "documents": {"source-1": {"status": "published", "chunk_count": 2}},
                "evaluation": "not_started",
            }
        ),
        encoding="utf-8",
    )

    migrated = batch._state(state_path, manifest)

    assert migrated["schema_version"] == 2
    assert migrated["documents"] == {
        batch._document_state_key("source-1", "v1"): {"status": "published", "chunk_count": 2}
    }


def test_버전이_모호한_기존_상태는_변경하지_않고_재개를_거부한다(tmp_path: Path) -> None:
    manifest_path, state_path, _ = _files(tmp_path)
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["documents"][1]["source_id"] = "source-1"
    manifest_data["documents"][1]["version"] = "v2"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    manifest = batch._manifest(manifest_path)
    fingerprint = batch.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    old_state = {
        "schema_version": 1,
        "manifest_sha256": fingerprint,
        "documents": {"source-1": {"status": "published", "chunk_count": 2}},
        "evaluation": "not_started",
    }
    state_path.write_text(json.dumps(old_state), encoding="utf-8")
    before = state_path.read_bytes()

    try:
        batch._state(state_path, manifest)
    except batch.BatchError as exc:
        assert "안전하게 구분" in str(exc)
    else:
        raise AssertionError("버전이 모호한 이전 상태를 재개했습니다.")

    assert state_path.read_bytes() == before


def test_상태의_문서_단계가_손상되면_재개를_거부한다(tmp_path: Path) -> None:
    manifest_path, state_path, _ = _files(tmp_path)
    manifest = batch._manifest(manifest_path)
    fingerprint = batch.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "manifest_sha256": fingerprint,
                "documents": {batch._document_state_key("source-1", "v1"): {"status": []}},
                "evaluation": "not_started",
            }
        ),
        encoding="utf-8",
    )

    try:
        batch._state(state_path, manifest)
    except batch.BatchError as exc:
        assert "안전하게 해석" in str(exc)
    else:
        raise AssertionError("손상된 상태를 재개했습니다.")


def test_배치_평가_보고서는_경로를_지정하지_않으면_표준출력에만_출력한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["evaluation"] = {"cases": "cases.csv", "gold": "gold.json"}
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    report_path = state.with_suffix(".evaluation.json")
    report = {
        "status": "complete",
        "document_metrics": {"document_hit_at_10": 1.0},
        "evidence_metrics": {"recall_at_10": 1.0},
    }
    stdout = StringIO()

    with (
        patch("starter_rag.batch.database_url_from_environment", return_value="local-test-url"),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(batch, "evaluate_cases", return_value=report),
        patch("sys.stdout", stdout),
    ):
        assert batch.run_batch(manifest, state, phase="evaluate") == 0

    assert not report_path.exists()
    assert json.loads(stdout.getvalue())["report"] is None


def test_배치_평가_보고서는_지정한_경로에_저장한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["evaluation"] = {"cases": "cases.csv", "gold": "gold.json"}
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    output = tmp_path / "reports" / "evaluation.json"
    report = {
        "status": "complete",
        "document_metrics": {"document_hit_at_10": 1.0},
        "evidence_metrics": {"recall_at_10": 1.0},
    }

    with (
        patch("starter_rag.batch.database_url_from_environment", return_value="local-test-url"),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(batch, "evaluate_cases", return_value=report),
    ):
        assert (
            batch.run_batch(
                manifest,
                state,
                phase="evaluate",
                evaluation_output_path=output,
            )
            == 0
        )

    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_평가_실패는_이전_완료_상태를_실패로_갱신한다(tmp_path: Path) -> None:
    manifest, state, _ = _files(tmp_path)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["evaluation"] = {"cases": "cases.csv", "gold": "gold.json"}
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    report = {
        "status": "complete",
        "document_metrics": {"document_hit_at_10": 1.0},
        "evidence_metrics": {"recall_at_10": 1.0},
    }

    with (
        patch("starter_rag.batch.database_url_from_environment", return_value="local-test-url"),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(batch, "evaluate_cases", return_value=report),
    ):
        assert batch.run_batch(manifest, state, phase="evaluate") == 0

    assert json.loads(state.read_text(encoding="utf-8"))["evaluation"] == "complete"
    with (
        patch("starter_rag.batch.database_url_from_environment", return_value="local-test-url"),
        patch.object(batch, "_published_version_identity", return_value=None),
        patch.object(
            batch, "evaluate_cases", side_effect=RuntimeError("private evaluation failure")
        ),
    ):
        try:
            batch.run_batch(manifest, state, phase="evaluate")
        except batch.BatchError as exc:
            assert "RuntimeError" in str(exc)
            assert "private evaluation failure" not in str(exc)
        else:
            raise AssertionError("평가 오류가 성공으로 처리됐습니다.")

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["evaluation"] == "failed"
    assert saved["evaluation_error_type"] == "RuntimeError"


def test_배치_CLI가_명시한_평가_출력_경로를_실행기로_전달한다(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    state = tmp_path / "state.json"
    output = tmp_path / "evaluation.json"

    with patch.object(batch, "run_batch", return_value=0) as run_batch:
        assert (
            rag_cli.main(
                [
                    "batch",
                    str(manifest),
                    "--state",
                    str(state),
                    "--phase",
                    "evaluate",
                    "--evaluation-out",
                    str(output),
                ]
            )
            == 0
        )

    run_batch.assert_called_once_with(
        manifest,
        state,
        phase="evaluate",
        prepare_workers=2,
        evaluation_output_path=output,
    )


def test_배치_명령이_끝나면_진행률_환경값을_복원한다() -> None:
    def cli_main(_arguments):
        assert os.environ.get("RAG_PROGRESS") == "1"
        print("{}")
        return 0

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("starter_rag.cli.main", side_effect=cli_main),
    ):
        assert batch._capture_cli(["status"], progress=True) == (0, {})
        assert "RAG_PROGRESS" not in os.environ


def test_청크_식별자_재매핑이_필요하면_근거_지표를_생략한다(tmp_path: Path) -> None:
    cases = tmp_path / "cases.csv"
    cases.write_text(
        "id,question\n" + "".join(f"case-{i:02d},Question {i}\n" for i in range(1, 3)),
        encoding="utf-8",
    )
    queries = [
        {
            "query_id": f"case-{i:02d}",
            "question": f"Question {i}",
            "expected_source_id": "source-a",
            "gold_evidence_ids": [f"gold-{i}"],
        }
        for i in range(1, 3)
    ]
    gold = tmp_path / "gold.json"
    gold.write_text(
        json.dumps(
            {
                "queries": queries
                + [
                    {"query_id": "excluded-01", "gold_evidence_ids": []},
                    {"query_id": "excluded-02", "gold_evidence_ids": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    def search(arguments):
        print(
            json.dumps(
                {
                    "success": True,
                    "evidence": [{"evidence_id": "new-id", "source": {"source_id": "source-a"}}],
                }
            )
        )
        return 0

    with (
        patch.object(batch, "_gold_ids_present", return_value=set()),
        patch("starter_rag.cli.main", side_effect=search),
    ):
        report = batch.evaluate_cases(cases, gold, "published-guides")
    assert report["status"] == "gold_ids_unmapped"
    assert report["total"] == report["completed"] == 2
    assert report["document_metrics"]["document_hit_at_10"] == 1.0
    assert report["evidence_metrics"]["recall_at_10"] is None
    assert len(report["missing_gold_evidence_ids"]) == 2


def test_평가_지표는_공통_계산을_사용하고_중복_결과를_한번만_집계한다(tmp_path: Path) -> None:
    cases = tmp_path / "cases.csv"
    cases.write_text("id,question\ncase-01,Question 1\n", encoding="utf-8")
    gold = tmp_path / "gold.json"
    gold.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query_id": "case-01",
                        "question": "Question 1",
                        "expected_source_id": "source-a",
                        "gold_evidence_ids": ["gold-1", "gold-2"],
                    },
                    {"query_id": "SI01-01", "gold_evidence_ids": []},
                    {"query_id": "SI01-04", "gold_evidence_ids": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    def search(_arguments):
        print(
            json.dumps(
                {
                    "evidence": [
                        {"evidence_id": "other", "source": {"source_id": "source-x"}},
                        {"evidence_id": "gold-1", "source": {"source_id": "source-a"}},
                        {"evidence_id": "gold-1", "source": {"source_id": "source-a"}},
                        {"evidence_id": "gold-2", "source": {"source_id": "source-b"}},
                    ]
                }
            )
        )
        return 0

    with (
        patch.object(batch, "_gold_ids_present", return_value={"gold-1", "gold-2"}),
        patch("starter_rag.cli.main", side_effect=search),
    ):
        report = batch.evaluate_cases(cases, gold, "published-guides")

    row = report["cases"][0]
    assert row["recall_at_3"] == 0.5
    assert row["recall_at_5"] == 1.0
    assert row["recall_at_10"] == 1.0
    assert row["mrr_at_10"] == 0.5
    assert row["full_evidence_coverage_at_10"] == 1
    assert row["document_hit_at_3"] == 1
    assert row["document_mrr_at_10"] == 0.5
    assert report["excluded_questions"] == ["SI01-01", "SI01-04"]


def test_저장소_DB오류는_비밀값없이_안전한_배치오류로_변환한다() -> None:
    async def query(_source_id: str, _version: str) -> batch._PublishedVersionIdentity | None:
        raise OperationalError("SELECT", {}, RuntimeError("password=synthetic-secret"))

    database = SimpleNamespace(close=AsyncMock())
    store = SimpleNamespace(_published_version_identity=query)
    with (
        patch.object(batch, "database_url_from_environment", return_value="local-test-url"),
        patch.object(batch, "PostgresRagDatabase", return_value=database),
        patch.object(batch, "PostgresPublicationStore", return_value=store),
    ):
        try:
            batch._published_version_identity("source-a", "v1", "collection-a")
        except batch.BatchError as exc:
            assert "로컬 DB 조회 실패" in str(exc)
            assert "synthetic-secret" not in str(exc)
        else:
            raise AssertionError("PostgreSQL 오류가 BatchError로 변환되지 않았습니다.")

    database.close.assert_awaited_once()


def test_정답_근거_식별자_조회는_선택한_벡터_컬렉션을_사용한다() -> None:
    query_ids = AsyncMock(return_value={"gold-a", "gold-b"})
    vector_store = SimpleNamespace(_published_chunk_ids=query_ids)

    def read_vector_store(collection_id, query):
        assert collection_id == "collection-a"
        return asyncio.run(query(vector_store))

    with patch.object(batch, "_read_vector_store", side_effect=read_vector_store):
        ids = batch._gold_ids_present({"gold-b", "gold-a"}, "collection-a")

    assert ids == {"gold-a", "gold-b"}
    query_ids.assert_awaited_once_with(["gold-a", "gold-b"])
