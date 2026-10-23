# 책임: [D] RAG 패키지의 독립 CLI 진입점.
# 구현할 기능: 공개 검색과 Source_v2 검증·적재·평가를 명시적으로 실행한다.
# 코드 경계: startup 시 자동 적재하지 않고 승인된 로컬 RAG DB만 사용한다.
# 완료 기준: Source_v2 검증·색인·평가와 기존 게시·검색 명령을 명시적으로 실행한다.
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from starter_rag.contracts.models import DocumentVersion, SearchRequest, SourceRef
from starter_rag.embedding.model import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_REVISION,
    EmbeddingGemma,
)
from starter_rag.evaluation.golden_set import evaluate_source_v2_golden
from starter_rag.ingestion.chunking import DEFAULT_TARGET_TOKENS, DocumentChunk
from starter_rag.ingestion.chunking_model import (
    ChunkingModelConfigurationError,
    ChunkingModelInitializationError,
)
from starter_rag.ingestion.parser import (
    DocumentReadError,
    DocumentStructure,
    SourceV2Error,
    UnsupportedDocumentFormatError,
    extract_document_structure,
    inspect_source_v2,
    parse_document,
)
from starter_rag.ingestion.service import (
    SOURCE_V2_TEST_COLLECTION,
    chunk_document_with_config,
    index_source_v2,
    verify_source_rows,
)
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    PostgresRagDatabase,
    database_url_from_environment,
)
from starter_rag.storage.models import DEFAULT_COLLECTION_ID, SCHEMA_NAME, TABLE_NAME
from starter_rag.storage.publication import PostgresPublicationStore
from starter_rag.storage.vector_store import PGVectorStore


def _file_argument(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("파일 경로가 비어 있습니다")
    return value


def _tokenizer_path(cli_path: str | None) -> str:
    path = cli_path if cli_path is not None else os.environ.get("RAG_TOKENIZER_PATH")
    if path is None or not path.strip():
        raise ValueError("토크나이저 경로를 지정하세요: --tokenizer-path 또는 RAG_TOKENIZER_PATH")
    return path


def _parse_file(path: str) -> int:
    source = Path(path)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            document = parse_document(source)
            structure = extract_document_structure(document, source)
        payload = {
            "input_file": path,
            "success": True,
            "source_format": structure.source_format,
            "element_count": len(structure.elements),
            "elements": [asdict(element) for element in structure.elements],
            "unverified_items": [asdict(item) for item in structure.unverified_items],
        }
        output = json.dumps(payload, ensure_ascii=False)
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 파서 오류는 CLI 사용자에게 표시한다.
        print(f"문서 파싱에 실패했습니다: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("양의 정수를 입력해야 합니다") from None
    if result <= 0:
        raise argparse.ArgumentTypeError("양의 정수를 입력해야 합니다")
    return result


def _https_url(value: str) -> str:
    if not value.startswith("https://"):
        raise argparse.ArgumentTypeError("공식 출처 URL은 https://로 시작해야 합니다")
    return value


def _load_tokenizer(path: str):
    # 로컬 파일 또는 이미 캐시된 토크나이저만 불러오며 원격으로 내려받지 않는다.
    try:
        from transformers import AutoTokenizer
    except ImportError:
        raise RuntimeError(
            "토크나이저를 불러오려면 RAG의 transformers 의존성이 필요합니다."
        ) from None

    try:
        return AutoTokenizer.from_pretrained(
            path,
            local_files_only=True,
            trust_remote_code=False,
        )
    except Exception:  # noqa: BLE001 - 로컬 캐시 오류에 내부 구현 정보가 포함될 수 있다.
        raise ValueError(
            "로컬 토크나이저를 불러오지 못했습니다. 다운로드된 토크나이저 경로를 확인하세요."
        ) from None


def _chunk_summary(chunk: DocumentChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "kind": chunk.kind,
        "element_ids": chunk.element_ids,
        "text": chunk.text,
        "content_sha256": chunk.content_sha256,
        "locations": [asdict(location) for location in chunk.locations],
        "table_row": asdict(chunk.table_row) if chunk.table_row is not None else None,
        "token_count": chunk.token_count,
        "over_target": chunk.over_target,
        "generation_method": chunk.generation_method,
        "model_status": chunk.model_status,
        "model_attempts": chunk.model_attempts,
        "model_failure": chunk.model_failure,
        "fallback_used": chunk.fallback_used,
    }


def _chunk_file(
    path: str,
    *,
    tokenizer_path: str,
    source_id: str | None,
    version: str,
    target_tokens: int,
) -> int:
    source = Path(path)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            document = parse_document(source)
            structure: DocumentStructure = extract_document_structure(document, source)
            try:
                tokenizer = _load_tokenizer(tokenizer_path)
            except ValueError:
                print("로컬 토크나이저 경로 또는 설정을 확인하세요.", file=sys.stderr)
                return 2

            def count_tokens(text: str) -> int:
                return len(tokenizer.encode(text, add_special_tokens=False))

            try:
                chunks = asyncio.run(
                    chunk_document_with_config(
                        structure,
                        source_id=source_id or source.name,
                        version=version,
                        count_tokens=count_tokens,
                        target_tokens=target_tokens,
                    )
                )
            except (ChunkingModelConfigurationError, ChunkingModelInitializationError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            except ValueError:
                print("RAG 공급자 설정 또는 청킹 입력이 올바르지 않습니다.", file=sys.stderr)
                return 2
        payload = {
            "input_file": path,
            "success": True,
            "source_format": structure.source_format,
            "source_id": source_id or source.name,
            "version": version,
            "tokenizer": Path(tokenizer_path).name,
            "chunk_count": len(chunks),
            "chunks": [_chunk_summary(chunk) for chunk in chunks],
        }
        output = json.dumps(payload, ensure_ascii=False)
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError:
        print("문서 청킹 입력이 올바르지 않습니다.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 공급자 인증 정보가 있을 수 있어 예외 원문을 출력하지 않는다.
        print(f"청킹 실행에 실패했습니다: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(output)
    return 0


async def _database_for_command():
    return PostgresRagDatabase(database_url_from_environment())


def _database_is_configured() -> bool:
    try:
        database_url_from_environment()
    except DatabaseConfigurationError:
        return False
    return True


def _database_init() -> int:
    async def run() -> dict[str, object]:
        database = await _database_for_command()
        try:
            await database.initialize()
            async with database.sql_engine.connect() as connection:
                from sqlalchemy import text

                result = await connection.execute(
                    text(
                        """SELECT current_database() AS database_name,
                        current_setting('server_version') AS postgres_version,
                        (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS pgvector_version"""
                    )
                )
                info = result.mappings().one()
            return {
                "success": True,
                "database": info["database_name"],
                "postgresVersion": info["postgres_version"],
                "pgvectorVersion": info["pgvector_version"],
                "schema": SCHEMA_NAME,
                "table": TABLE_NAME,
                "primaryKey": "chunk_id TEXT",
                "dimension": EMBEDDING_DIMENSION,
            }
        finally:
            await database.close()

    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False))
    except DatabaseConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - never print a URL or driver credentials.
        print(f"로컬 RAG DB 초기화 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


def _index_file(
    path: str,
    *,
    tokenizer_path: str,
    source_id: str,
    version: str,
    source_title: str,
    source_url: str | None,
    publisher: str,
    collection_id: str,
    target_tokens: int,
    is_synthetic: bool,
) -> int:
    source_path = Path(path)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            source_bytes = source_path.read_bytes()
            document = parse_document(source_path)
            structure = extract_document_structure(document, source_path)
            tokenizer = _load_tokenizer(tokenizer_path)

            def count_tokens(value: str) -> int:
                return len(tokenizer.encode(value, add_special_tokens=False))

            chunks = asyncio.run(
                chunk_document_with_config(
                    structure,
                    source_id=source_id,
                    version=version,
                    count_tokens=count_tokens,
                    target_tokens=target_tokens,
                )
            )
        source = SourceRef(
            source_id=source_id,
            title=source_title,
            url=source_url,
            publisher=publisher,
            version=version,
        )
        document_version = DocumentVersion(
            source=source,
            content_sha256=sha256(source_bytes).hexdigest(),
            state="staging",
            chunk_count=len(chunks),
        )

        async def index() -> dict[str, object]:
            database = await _database_for_command()
            try:
                store = PGVectorStore(
                    database,
                    EmbeddingGemma(),
                    collection_id=collection_id,
                )
                outcome = await store.index_document(
                    document_version,
                    chunks,
                    is_synthetic=is_synthetic,
                )
                return {
                    "success": True,
                    "sourceId": outcome.source_id,
                    "version": outcome.version,
                    "collectionId": outcome.collection_id,
                    "chunkCount": outcome.chunk_count,
                    "state": outcome.state,
                    "skippedExistingVersion": outcome.skipped,
                    "modelId": EMBEDDING_MODEL_ID,
                    "modelRevision": EMBEDDING_MODEL_REVISION,
                    "dimension": EMBEDDING_DIMENSION,
                    "synthetic": is_synthetic,
                }
            finally:
                await database.close()

        print(json.dumps(asyncio.run(index()), ensure_ascii=False))
        return 0
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (
        DatabaseConfigurationError,
        ValueError,
        ChunkingModelConfigurationError,
        ChunkingModelInitializationError,
    ) as exc:
        print(f"잘못된 RAG 적재 요청: {type(exc).__name__}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - exception text may contain credentials.
        print(f"RAG 적재 실패: {type(exc).__name__}", file=sys.stderr)
        return 1


def _publish(source_id: str, version: str, collection_id: str) -> int:
    async def run() -> dict[str, object]:
        database = await _database_for_command()
        try:
            document = await PostgresPublicationStore(
                database,
                collection_id=collection_id,
            ).publish(source_id, version)
            return {
                "success": True,
                "sourceId": document.source.source_id,
                "version": document.source.version,
                "state": document.state,
                "chunkCount": document.chunk_count,
                "contentSha256": document.content_sha256,
            }
        finally:
            await database.close()

    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False))
    except DatabaseConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - database details can include connection data.
        print(f"게시 전환 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


def _search(query: str, top_k: int, collection_id: str, allow_synthetic: bool) -> int:
    try:
        request = SearchRequest(query=query, top_k=top_k)
    except ValueError as exc:
        print(f"잘못된 RAG 검색 요청: {exc}", file=sys.stderr)
        return 2

    async def run() -> dict[str, object]:
        database = await _database_for_command()
        try:
            store = PGVectorStore(database, EmbeddingGemma(), collection_id=collection_id)
            from starter_rag.retrieval.search import PGVectorSearch

            result = await PGVectorSearch(
                store,
                store.embedding,
                allow_synthetic=allow_synthetic,
            ).search(request)
            return {
                "success": True,
                "query": request.query,
                "topK": request.top_k,
                "collectionId": collection_id,
                "evidence": [asdict(item) for item in result.evidence],
            }
        finally:
            await database.close()

    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False))
    except DatabaseConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - never disclose credentials in exceptions.
        print(f"RAG 검색 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-rag",
        description="문서 파싱·청킹·색인·게시·검색과 Source_v2 검증 CLI",
    )
    cmd = parser.add_subparsers(dest="command", required=True)
    cmd.add_parser("status", help="구현 상태와 DB 설정 확인 (DB 연결 없음)")

    parse = cmd.add_parser("parse", help="문서 구조와 원문 위치를 JSON으로 출력 (DB 미사용)")
    parse.add_argument("path", type=_file_argument, metavar="PATH")

    chunk = cmd.add_parser("chunk", help="문서를 청킹해 결과 JSON 출력 (DB 미사용)")
    chunk.add_argument("path", type=_file_argument, metavar="PATH")
    chunk.add_argument(
        "--tokenizer-path",
        type=_file_argument,
        metavar="PATH",
        help="필요: CLI 경로 우선, 없으면 RAG_TOKENIZER_PATH 사용 (로컬 전용)",
    )
    chunk.add_argument("--source-id", help="Source ID (기본값: 파일명)")
    chunk.add_argument("--version", default="cli-test", help="문서 버전 (기본값: cli-test)")
    chunk.add_argument(
        "--target-tokens",
        type=_positive_integer,
        default=DEFAULT_TARGET_TOKENS,
        help=f"일반 문서 청크 목표 토큰 수 (기본값: {DEFAULT_TARGET_TOKENS})",
    )

    cmd.add_parser("db-init", help="승인된 로컬 DB 스키마 준비 (DB 변경)")

    index = cmd.add_parser(
        "index",
        help=(
            "문서를 색인만 합니다. standard는 출처 정보가 필요합니다. "
            "검색에 공개하려면 publish를 별도 실행합니다"
        ),
    )
    index.add_argument("path", type=_file_argument, metavar="PATH")
    index.add_argument(
        "--type",
        choices=("standard", "source-v2"),
        default="standard",
        help="색인 종류 (기본값: standard)",
    )
    index.add_argument(
        "--tokenizer-path",
        type=_file_argument,
        metavar="PATH",
        help="필요: CLI 경로 우선, 없으면 RAG_TOKENIZER_PATH 사용 (로컬 전용)",
    )
    index.add_argument("--source-id", help="standard 필수 출처 ID")
    index.add_argument("--version", help="standard 필수 문서 버전")
    index.add_argument("--source-title", help="standard 필수 출처 제목")
    index.add_argument("--source-url", type=_https_url, help="선택 출처 URL (HTTPS만 허용)")
    index.add_argument("--publisher", help="standard 필수 발행처")
    index.add_argument(
        "--collection-id",
        help=(
            "색인 collection (기본값: standard는 published-guides, "
            "source-v2는 rag-test-source-v2-e2e)"
        ),
    )
    index.add_argument(
        "--target-tokens",
        type=_positive_integer,
        default=DEFAULT_TARGET_TOKENS,
        help=f"일반 문서 청크 목표 토큰 수 (기본값: {DEFAULT_TARGET_TOKENS})",
    )
    index.add_argument(
        "--synthetic", action="store_true", help="합성 시험자료로 표시; 별도 collection 필수"
    )

    publish = cmd.add_parser("publish", help="완전히 색인된 문서 버전을 원자적으로 게시")
    publish.add_argument("--source-id", required=True)
    publish.add_argument("--version", required=True)
    publish.add_argument(
        "--collection-id", default=DEFAULT_COLLECTION_ID, help="기본값: published-guides"
    )

    search = cmd.add_parser("search", help="게시된 pgvector 자료를 검색")
    search.add_argument("query", metavar="QUERY")
    search.add_argument("--top-k", type=int, default=3, help="검색 결과 수 1~10 (기본값: 3)")
    search.add_argument(
        "--collection-id", default=DEFAULT_COLLECTION_ID, help="기본값: published-guides"
    )
    search.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="격리된 테스트 collection의 합성자료를 검색 (기본값: 제외)",
    )
    check = cmd.add_parser(
        "check", help="Source_v2 필수값·URL·승인 검증 (DB 미사용, --rows로 원본 행 확인)"
    )
    check.add_argument("path", type=_file_argument, metavar="PATH")
    check.add_argument("--rows", action="store_true", help="Docling 행 대응과 결정적 청킹도 확인")
    check.add_argument(
        "--tokenizer-path",
        type=_file_argument,
        metavar="PATH",
        help="--rows에 필요: CLI 경로 우선, 없으면 RAG_TOKENIZER_PATH (로컬 전용)",
    )

    evaluate = cmd.add_parser("test", help="Golden Truth v1.2 검색 품질 평가 (DB 쓰기 없음)")
    evaluate.add_argument("--dataset", type=Path, help="평가 JSON (기본값: Golden Truth v1.2)")
    evaluate.add_argument("--out", type=Path, help="평가 결과 JSON 경로")
    evaluate.add_argument(
        "--mode",
        choices=("clarified", "title"),
        default="clarified",
        help="검색 질의 종류 (기본값: clarified)",
    )
    evaluate.add_argument(
        "--group",
        choices=("all", "direct", "partial", "safety_context"),
        default="all",
        help="평가 질문 그룹 (기본값: all)",
    )
    evaluate.add_argument(
        "--validate-only", action="store_true", help="평가 자료만 검증 (DB 사용 안 함)"
    )
    args = parser.parse_args(argv)

    if args.command == "status":
        print(
            json.dumps(
                {
                    "package": "starter-rag",
                    "status": "implemented",
                    "searchImplemented": True,
                    "ingestionImplemented": True,
                    "databaseConfigured": _database_is_configured(),
                    "runtimeReadiness": "not-checked",
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "parse":
        return _parse_file(args.path)
    if args.command == "chunk":
        try:
            tokenizer_path = _tokenizer_path(args.tokenizer_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return _chunk_file(
            args.path,
            tokenizer_path=tokenizer_path,
            source_id=args.source_id,
            version=args.version,
            target_tokens=args.target_tokens,
        )
    if args.command == "db-init":
        return _database_init()
    if args.command == "index":
        if args.type == "standard":
            required_metadata = {
                "--source-id": args.source_id,
                "--version": args.version,
                "--source-title": args.source_title,
                "--publisher": args.publisher,
            }
            missing = [name for name, value in required_metadata.items() if not value]
            if missing:
                parser.error(
                    f"--type standard에는 필수 출처 정보가 필요합니다: {', '.join(missing)}"
                )
        elif args.synthetic:
            parser.error("Source_v2 색인에는 --synthetic을 사용할 수 없습니다")

        collection_id = args.collection_id or (
            SOURCE_V2_TEST_COLLECTION if args.type == "source-v2" else DEFAULT_COLLECTION_ID
        )
        try:
            tokenizer_path = _tokenizer_path(args.tokenizer_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        if args.type == "source-v2":
            try:
                tokenizer = _load_tokenizer(tokenizer_path)

                def count_tokens(value: str) -> int:
                    return len(tokenizer.encode(value, add_special_tokens=False))

                result = asyncio.run(
                    index_source_v2(
                        args.path,
                        count_tokens=count_tokens,
                        collection_id=collection_id,
                    )
                )
                print(json.dumps(result, ensure_ascii=False))
                return 0
            except (SourceV2Error, FileNotFoundError, UnsupportedDocumentFormatError) as error:
                print(f"Source_v2 입력 검증 실패: {error}", file=sys.stderr)
                return 2
            except (DatabaseConfigurationError, ValueError, OSError) as error:
                print(f"Source_v2 실행 설정 오류: {type(error).__name__}", file=sys.stderr)
                return 2
            except Exception as error:  # noqa: BLE001 - 예외 내용에 연결 정보가 포함될 수 있다.
                print(f"Source_v2 색인 실패: {type(error).__name__}", file=sys.stderr)
                return 1

        if args.synthetic and "합성 시험 자료" not in args.source_title:
            parser.error("--synthetic 제목에는 '합성 시험 자료' 표시가 필요합니다")
        if args.synthetic and collection_id == DEFAULT_COLLECTION_ID:
            parser.error(
                "합성 시험자료는 기본 published-guides가 아닌 별도 collection에 적재해야 합니다"
            )
        return _index_file(
            args.path,
            tokenizer_path=tokenizer_path,
            source_id=args.source_id,
            version=args.version,
            source_title=args.source_title,
            source_url=args.source_url,
            publisher=args.publisher,
            collection_id=collection_id,
            target_tokens=args.target_tokens,
            is_synthetic=args.synthetic,
        )
    if args.command == "publish":
        return _publish(args.source_id, args.version, args.collection_id)
    if args.command == "search":
        return _search(args.query, args.top_k, args.collection_id, args.allow_synthetic)
    if args.command == "check":
        try:
            report = inspect_source_v2(args.path)
            safe_report = {key: value for key, value in report.items() if key != "source_units"}
            payload = {**safe_report, "db_write": False}
            if args.rows:
                try:
                    tokenizer_path = _tokenizer_path(args.tokenizer_path)
                    tokenizer = _load_tokenizer(tokenizer_path)
                except ValueError:
                    print(
                        "로컬 토크나이저 경로 또는 RAG_TOKENIZER_PATH 설정을 확인하세요.",
                        file=sys.stderr,
                    )
                    return 2

                def count_tokens(value: str) -> int:
                    return len(tokenizer.encode(value, add_special_tokens=False))

                units, rows = asyncio.run(verify_source_rows(args.path, count_tokens=count_tokens))
                payload.update(
                    {
                        "verified_units": len(units),
                        "verified_table_rows": len(rows),
                        "chunk_kind": "table_row",
                        "generation_method": "deterministic",
                        "model_calls_for_table_rows": 0,
                    }
                )
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        except (SourceV2Error, FileNotFoundError, UnsupportedDocumentFormatError) as error:
            print(f"Source_v2 입력 검증 실패: {error}", file=sys.stderr)
            return 2
        except (ValueError, OSError) as error:
            print(f"Source_v2 실행 설정 오류: {type(error).__name__}", file=sys.stderr)
            return 2
        except Exception as error:  # noqa: BLE001 - 예외 내용에 연결 정보가 포함될 수 있다.
            print(f"Source_v2 실행 실패: {type(error).__name__}", file=sys.stderr)
            return 1
    if args.command == "test":
        return evaluate_source_v2_golden(
            dataset_path=args.dataset,
            mode=args.mode,
            group=args.group,
            out_path=args.out,
            validate_only=args.validate_only,
        )
    parser.error("지원하지 않는 명령입니다")


if __name__ == "__main__":
    raise SystemExit(main())
