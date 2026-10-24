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
from dataclasses import asdict, dataclass
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
    index_mapped_xlsx,
    index_source_v2,
    verify_source_rows,
)
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    PostgresRagDatabase,
    database_url_from_environment,
)
from starter_rag.storage.models import DEFAULT_COLLECTION_ID, SCHEMA_NAME, TABLE_NAME
from starter_rag.storage.publication import (
    PostgresPublicationStore,
    PublicationError,
    PublicationInspection,
    PublicationOutcome,
)
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
        raise ValueError(
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


async def _database_for_profile(profile: str):
    """Use the local CLI by default; remote DB requires explicit opt-in and TLS."""
    if profile == "local":
        return await _database_for_command()
    if profile != "supabase":
        raise DatabaseConfigurationError("unsupported database profile")
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError
    from sqlalchemy.ext.asyncio import create_async_engine

    from starter_rag.storage.models import RagTableTarget

    raw_url = os.environ.get("DATABASE_URL", "").strip()
    try:
        url = make_url(raw_url)
    except ArgumentError:
        raise DatabaseConfigurationError("invalid DATABASE_URL") from None
    if (
        url.drivername != "postgresql+asyncpg"
        or url.port != 5432
        or not url.host
        or not url.host.endswith(".pooler.supabase.com")
    ):
        raise DatabaseConfigurationError("Supabase Session Pooler 5432 URL required")
    schema = os.environ.get("RAG_DB_SCHEMA", "rag")
    table = os.environ.get("RAG_VECTOR_TABLE", "chunks")
    if (schema, table) != ("rag", "chunks"):
        raise DatabaseConfigurationError("approved target must be rag.chunks")
    engine = create_async_engine(raw_url, connect_args={"ssl": "require"}, pool_pre_ping=True)
    try:
        db = PostgresRagDatabase.from_engine(engine, target=RagTableTarget(schema, table))
        await db.validate_existing_table()
    except BaseException:
        await engine.dispose()
        raise
    return db


async def _release_profile_database(database, profile: str) -> None:
    if profile == "supabase":
        await database.sql_engine.dispose()
    else:
        await database.close()


def _collection_for_profile(profile: str, requested: str | None) -> str:
    if profile == "supabase":
        configured = os.environ.get("RAG_COLLECTION_ID", "").strip()
        if not configured or requested != configured:
            raise DatabaseConfigurationError("explicit approved RAG_COLLECTION_ID required")
        return configured
    return requested or DEFAULT_COLLECTION_ID


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
    db_profile: str = "local",
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
            database = await _database_for_profile(db_profile)
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
                await _release_profile_database(database, db_profile)

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


def _index_mapped_file(
    path: str,
    *,
    mapping_path: str,
    tokenizer_path: str,
    collection_id: str,
    db_profile: str,
) -> int:
    try:
        with contextlib.redirect_stdout(sys.stderr):
            mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
            tokenizer = _load_tokenizer(tokenizer_path)

            def count_tokens(value: str) -> int:
                return len(tokenizer.encode(value, add_special_tokens=False))

        async def run():
            database = await _database_for_profile(db_profile)
            try:
                return await index_mapped_xlsx(
                    path,
                    mapping,
                    count_tokens=count_tokens,
                    database=database,
                    collection_id=collection_id,
                )
            finally:
                await _release_profile_database(database, db_profile)

        print(json.dumps(asyncio.run(run()), ensure_ascii=False))
        return 0
    except (ValueError, OSError, DatabaseConfigurationError, json.JSONDecodeError):
        print("XLSX mapping or database profile is invalid", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - connection credentials must not leak.
        print(f"mapped XLSX indexing failed: {type(exc).__name__}", file=sys.stderr)
        return 1


def _publish(source_id: str, version: str, collection_id: str, db_profile: str = "local") -> int:
    async def run() -> dict[str, object]:
        database = await _database_for_profile(db_profile)
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
            await _release_profile_database(database, db_profile)

    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False))
    except DatabaseConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - database details can include connection data.
        print(f"게시 전환 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


@dataclass(frozen=True)
class _IndexResultItem:
    source_id: str
    version: str
    collection_id: str
    indexed_state: str


class _BatchPublicationInputError(ValueError):
    pass


class _BatchDatabaseUnavailable(RuntimeError):
    def __init__(
        self,
        error: BaseException,
        *,
        publication_state: str = "unknown",
        outcome: str = "failed",
    ) -> None:
        self.error_type = type(error).__name__
        self.sqlstate = _sqlstate(error)
        self.publication_state = publication_state
        self.outcome = outcome
        super().__init__("database unavailable")


def _required_index_result_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _BatchPublicationInputError(f"index result item requires {field}")
    return value


def _parse_index_result(payload: object) -> tuple[_IndexResultItem, ...]:
    if not isinstance(payload, dict):
        raise _BatchPublicationInputError("index result must be a JSON object")

    raw_items: list[tuple[object, object, object, object]] = []
    if "outcomes" in payload:
        outcomes = payload.get("outcomes")
        collection_id = _required_index_result_text(payload.get("collection_id"), "collection_id")
        indexed_units = payload.get("indexed_units")
        if (
            payload.get("published") is not False
            or not isinstance(outcomes, list)
            or not outcomes
            or type(indexed_units) is not int
            or indexed_units != len(outcomes)
        ):
            raise _BatchPublicationInputError("index result outcomes are incomplete or unpublished")
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                raise _BatchPublicationInputError("index result outcome must be an object")
            raw_items.append(
                (
                    outcome.get("source_id"),
                    outcome.get("version"),
                    collection_id,
                    outcome.get("indexed_state"),
                )
            )
    elif {"success", "sourceId", "version", "collectionId", "state"}.issubset(payload):
        if payload.get("success") is not True:
            raise _BatchPublicationInputError("standard index result did not succeed")
        raw_items.append(
            (
                payload.get("sourceId"),
                payload.get("version"),
                payload.get("collectionId"),
                payload.get("state"),
            )
        )
    else:
        raise _BatchPublicationInputError("unsupported index result format")

    items: list[_IndexResultItem] = []
    source_versions: dict[str, str] = {}
    for raw_source_id, raw_version, raw_collection_id, raw_state in raw_items:
        source_id = _required_index_result_text(raw_source_id, "source_id")
        version = _required_index_result_text(raw_version, "version")
        item_collection_id = _required_index_result_text(raw_collection_id, "collection_id")
        if raw_state not in ("indexed", "published"):
            raise _BatchPublicationInputError(
                f"index result for {source_id} has an incomplete index state"
            )
        if source_id in source_versions:
            if source_versions[source_id] != version:
                raise _BatchPublicationInputError(
                    f"source {source_id} appears with conflicting versions"
                )
            raise _BatchPublicationInputError(f"duplicate source {source_id} in index result")
        source_versions[source_id] = version
        items.append(_IndexResultItem(source_id, version, item_collection_id, raw_state))
    if not items:
        raise _BatchPublicationInputError("index result contains no source units")
    return tuple(items)


def _load_index_result(path: str) -> tuple[_IndexResultItem, ...]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _BatchPublicationInputError(
            "index result file is missing, unreadable or invalid JSON"
        ) from None
    return _parse_index_result(payload)


def _exception_chain(error: BaseException):
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attribute in ("orig", "__cause__", "__context__"):
            try:
                nested = getattr(current, attribute, None)
            except Exception:  # noqa: BLE001 - 드라이버 속성이 예외를 발생시킬 수 있다.
                nested = None
            if isinstance(nested, BaseException):
                pending.append(nested)
        try:
            nested_errors = getattr(current, "exceptions", ())
        except Exception:  # noqa: BLE001 - 드라이버 속성이 예외를 발생시킬 수 있다.
            nested_errors = ()
        if isinstance(nested_errors, (tuple, list)):
            pending.extend(nested for nested in nested_errors if isinstance(nested, BaseException))


def _sqlstate(error: BaseException) -> str | None:
    for current in _exception_chain(error):
        candidates = [current]
        try:
            diagnostic = getattr(current, "diag", None)
        except Exception:  # noqa: BLE001 - 드라이버 진단 정보가 없을 수 있다.
            diagnostic = None
        if diagnostic is not None:
            candidates.append(diagnostic)
        for candidate in candidates:
            for attribute in ("sqlstate", "pgcode"):
                try:
                    state = getattr(candidate, attribute, None)
                except Exception:  # noqa: BLE001 - 드라이버 진단 정보가 없을 수 있다.
                    state = None
                if (
                    isinstance(state, str)
                    and len(state) == 5
                    and state.isascii()
                    and state.isalnum()
                ):
                    return state.upper()
    return None


def _is_database_wide_error(error: BaseException) -> bool:
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

    for current in _exception_chain(error):
        if isinstance(current, SQLAlchemyTimeoutError):
            return True
        if isinstance(current, DBAPIError) and current.connection_invalidated:
            return True
    state = _sqlstate(error)
    return bool(state and (state.startswith("08") or state in {"57P01", "57P02", "57P03"}))


def _is_transient_database_error(error: BaseException) -> bool:
    if _is_database_wide_error(error):
        return True
    state = _sqlstate(error)
    return state in {"40001", "40P01", "55P03"}


async def _inspect_with_one_retry(
    store: PostgresPublicationStore,
    item: _IndexResultItem,
) -> PublicationInspection:
    try:
        return await store.inspect_version(item.source_id, item.version)
    except PublicationError:
        raise
    except Exception as error:  # noqa: BLE001 - 연결 상세 정보는 출력하지 않는다.
        if _is_database_wide_error(error) or not _is_transient_database_error(error):
            raise _BatchDatabaseUnavailable(error) from None
    try:
        return await store.inspect_version(item.source_id, item.version)
    except PublicationError:
        raise
    except Exception as error:  # noqa: BLE001 - 사전 조회 재실패 시 배치를 중단한다.
        raise _BatchDatabaseUnavailable(error) from None


async def _database_outage_after_publish(
    store: PostgresPublicationStore,
    item: _IndexResultItem,
    error: BaseException,
) -> _BatchDatabaseUnavailable:
    try:
        inspection = await store.inspect_version(item.source_id, item.version)
    except PublicationError:
        return _BatchDatabaseUnavailable(error, publication_state="unconfirmed")
    except Exception:  # noqa: BLE001 - 재확인 중 드라이버 오류 원문을 출력하지 않는다.
        return _BatchDatabaseUnavailable(error)
    if inspection.document.state == "published":
        return _BatchDatabaseUnavailable(
            error,
            publication_state="published",
            outcome="confirmed_after_error",
        )
    return _BatchDatabaseUnavailable(error, publication_state=inspection.document.state)


def _validate_replacement_policy(
    inspection: PublicationInspection,
    *,
    allow_version_replacement: bool,
) -> None:
    if inspection.document.state not in {"indexed", "published"}:
        raise PublicationError("only a complete indexed version can be published")
    if (
        inspection.document.state == "indexed"
        and inspection.published_versions
        and not allow_version_replacement
    ):
        raise PublicationError(
            "a different version is currently published; review the SHA version and "
            "rerun with --allow-version-replacement to retire it"
        )


async def _publish_with_one_retry(
    store: PostgresPublicationStore,
    item: _IndexResultItem,
    *,
    allow_version_replacement: bool,
) -> PublicationOutcome:
    async def publish() -> PublicationOutcome:
        return await store.publish_with_outcome(
            item.source_id,
            item.version,
            allow_version_replacement=allow_version_replacement,
        )

    try:
        return await publish()
    except PublicationError:
        raise
    except Exception as error:
        if _is_database_wide_error(error):
            raise await _database_outage_after_publish(store, item, error) from None
        if not _is_transient_database_error(error):
            raise
        initial_error = error

    try:
        inspection = await store.inspect_version(item.source_id, item.version)
    except PublicationError:
        raise
    except Exception as error:  # noqa: BLE001 - 상태를 확인할 수 없으면 배치를 중단한다.
        raise _BatchDatabaseUnavailable(error) from None
    if inspection.document.state == "published":
        return PublicationOutcome(
            inspection.document,
            "confirmed_after_error",
            error_type=type(initial_error).__name__,
            sqlstate=_sqlstate(initial_error),
        )
    _validate_replacement_policy(
        inspection,
        allow_version_replacement=allow_version_replacement,
    )

    try:
        return await publish()
    except PublicationError:
        raise
    except Exception as error:
        if _is_database_wide_error(error):
            raise await _database_outage_after_publish(store, item, error) from None
        if not _is_transient_database_error(error):
            raise
        retry_error = error

    try:
        inspection = await store.inspect_version(item.source_id, item.version)
    except PublicationError:
        raise
    except Exception as error:  # noqa: BLE001 - 확인할 수 없는 상태를 임의로 성공 처리하지 않는다.
        raise _BatchDatabaseUnavailable(error) from None
    if inspection.document.state == "published":
        return PublicationOutcome(
            inspection.document,
            "confirmed_after_error",
            error_type=type(retry_error).__name__,
            sqlstate=_sqlstate(retry_error),
        )
    raise PublicationError(
        "publication still has not completed after one retry; the version remains unpublished"
    )


def _batch_item_result(
    item: _IndexResultItem,
    outcome: str,
    *,
    error: str | None = None,
    retired_versions: tuple[str, ...] = (),
    publication_state: str | None = None,
    error_type: str | None = None,
    sqlstate: str | None = None,
    database_unavailable: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "sourceId": item.source_id,
        "version": item.version,
        "outcome": outcome,
    }
    if error is not None:
        result["error"] = error
    if publication_state is not None:
        result["publicationState"] = publication_state
    if error_type is not None:
        result["errorType"] = error_type
    if sqlstate is not None:
        result["sqlstate"] = sqlstate
    if database_unavailable:
        result["databaseUnavailable"] = True
    if retired_versions:
        result["retiredVersions"] = list(retired_versions)
    return result


def _batch_summary(
    items: tuple[_IndexResultItem, ...],
    results: list[dict[str, object] | None],
    collection_id: str,
) -> dict[str, object]:
    completed = [
        result if result is not None else _batch_item_result(item, "not_attempted")
        for item, result in zip(items, results, strict=True)
    ]
    published_count = sum(result["outcome"] == "published" for result in completed)
    skipped_count = sum(result["outcome"] == "already_published" for result in completed)
    confirmed_after_error_count = sum(
        result["outcome"] == "confirmed_after_error" for result in completed
    )
    failed_count = sum(result["outcome"] == "failed" for result in completed)
    not_attempted_count = sum(result["outcome"] == "not_attempted" for result in completed)
    database_unavailable_count = sum(
        result.get("databaseUnavailable") is True for result in completed
    )
    return {
        "success": (
            failed_count == 0
            and not_attempted_count == 0
            and confirmed_after_error_count == 0
            and database_unavailable_count == 0
        ),
        "collectionId": collection_id,
        "totalCount": len(items),
        "publishedCount": published_count,
        "skippedCount": skipped_count,
        "confirmedAfterErrorCount": confirmed_after_error_count,
        "failedCount": failed_count,
        "notAttemptedCount": not_attempted_count,
        "databaseUnavailableCount": database_unavailable_count,
        "items": completed,
    }


async def _publish_index_result_items(
    store: PostgresPublicationStore,
    items: tuple[_IndexResultItem, ...],
    collection_id: str,
    *,
    allow_version_replacement: bool,
) -> dict[str, object]:
    results: list[dict[str, object] | None] = [None] * len(items)
    inspections: list[PublicationInspection | None] = [None] * len(items)

    # 첫 게시 트랜잭션 전에 모든 대상을 읽고 검증한다.
    for index, item in enumerate(items):
        try:
            inspection = await _inspect_with_one_retry(store, item)
            _validate_replacement_policy(
                inspection,
                allow_version_replacement=allow_version_replacement,
            )
            inspections[index] = inspection
        except PublicationError as error:
            results[index] = _batch_item_result(item, "failed", error=str(error))
        except _BatchDatabaseUnavailable as error:
            results[index] = _batch_item_result(
                item,
                error.outcome,
                error="database unavailable during preflight; no batch items were published",
                publication_state=error.publication_state,
                error_type=error.error_type,
                sqlstate=error.sqlstate,
                database_unavailable=True,
            )
            return _batch_summary(items, results, collection_id)
        except Exception as error:  # noqa: BLE001 - 예외 원문에 인증정보가 있을 수 있다.
            results[index] = _batch_item_result(
                item,
                "failed",
                error=f"database preflight failed: {type(error).__name__}",
            )
            return _batch_summary(items, results, collection_id)

    for index, (item, inspection) in enumerate(zip(items, inspections, strict=True)):
        if results[index] is not None:
            continue
        if inspection is not None and inspection.document.state == "published":
            results[index] = _batch_item_result(item, "already_published")
            continue
        try:
            outcome = await _publish_with_one_retry(
                store,
                item,
                allow_version_replacement=allow_version_replacement,
            )
            results[index] = _batch_item_result(
                item,
                outcome.disposition,
                retired_versions=outcome.retired_versions,
                error=(
                    "publication confirmed after an error; commit attribution is uncertain"
                    if outcome.disposition == "confirmed_after_error"
                    else None
                ),
                publication_state=(
                    outcome.document.state
                    if outcome.disposition == "confirmed_after_error"
                    else None
                ),
                error_type=outcome.error_type,
                sqlstate=outcome.sqlstate,
            )
        except _BatchDatabaseUnavailable as error:
            results[index] = _batch_item_result(
                item,
                error.outcome,
                error=(
                    "database outage; publication status is "
                    f"{error.publication_state}; inspect before rerunning"
                ),
                publication_state=error.publication_state,
                error_type=error.error_type,
                sqlstate=error.sqlstate,
                database_unavailable=True,
            )
            break
        except PublicationError as error:
            results[index] = _batch_item_result(item, "failed", error=str(error))
        except Exception as error:  # noqa: BLE001 - 예외 원문에 인증정보가 있을 수 있다.
            results[index] = _batch_item_result(
                item,
                "failed",
                error=f"publication failed: {type(error).__name__}",
            )
    return _batch_summary(items, results, collection_id)


def _publish_from_index_result(
    path: str,
    collection_id: str,
    db_profile: str = "local",
    *,
    allow_version_replacement: bool = False,
) -> int:
    try:
        items = _load_index_result(path)
        mismatched = [item.source_id for item in items if item.collection_id != collection_id]
        if mismatched:
            raise _BatchPublicationInputError(
                "index result collection_id does not match the selected database collection"
            )
    except _BatchPublicationInputError as error:
        print(f"배치 게시 입력 오류: {error}", file=sys.stderr)
        return 2

    async def run() -> dict[str, object]:
        database = await _database_for_profile(db_profile)
        try:
            store = PostgresPublicationStore(database, collection_id=collection_id)
            return await _publish_index_result_items(
                store,
                items,
                collection_id,
                allow_version_replacement=allow_version_replacement,
            )
        finally:
            await _release_profile_database(database, db_profile)

    try:
        summary = asyncio.run(run())
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["success"] else 1
    except DatabaseConfigurationError as error:
        print(f"잘못된 RAG 게시 DB 설정: {type(error).__name__}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - DB 연결정보는 출력하지 않는다.
        if _is_database_wide_error(error):
            summary = _batch_summary(items, [None] * len(items), collection_id)
            summary.update(
                {
                    "success": False,
                    "databaseUnavailable": True,
                    "databaseUnavailableCount": 1,
                    "error": "database unavailable before item processing",
                    "errorType": type(error).__name__,
                    "publicationState": "unknown",
                }
            )
            state = _sqlstate(error)
            if state is not None:
                summary["sqlstate"] = state
            print(json.dumps(summary, ensure_ascii=False))
            return 1
        print(f"배치 게시 실행 실패: {type(error).__name__}", file=sys.stderr)
        return 1


def _search(
    query: str, top_k: int, collection_id: str, allow_synthetic: bool, db_profile: str = "local"
) -> int:
    try:
        request = SearchRequest(query=query, top_k=top_k)
    except ValueError as exc:
        print(f"잘못된 RAG 검색 요청: {exc}", file=sys.stderr)
        return 2

    async def run() -> dict[str, object]:
        database = await _database_for_profile(db_profile)
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
            await _release_profile_database(database, db_profile)

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
        choices=("standard", "source-v2", "mapped-xlsx"),
        default="standard",
        help="색인 종류 (기본값: standard)",
    )
    index.add_argument(
        "--tokenizer-path",
        type=_file_argument,
        metavar="PATH",
        help="필요: CLI 경로 우선, 없으면 RAG_TOKENIZER_PATH 사용 (로컬 전용)",
    )
    index.add_argument("--mapping", type=_file_argument, help="mapped-xlsx schema JSON")
    index.add_argument("--db-profile", choices=("local", "supabase"), default="local")
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

    publish = cmd.add_parser(
        "publish",
        help="색인 결과의 Source Unit을 검수 후 게시하거나 단일 버전을 게시",
    )
    publish.add_argument("--db-profile", choices=("local", "supabase"), default="local")
    publish_mode = publish.add_mutually_exclusive_group(required=True)
    publish_mode.add_argument("--source-id", help="단건 게시 Source ID")
    publish_mode.add_argument(
        "--from-index-result",
        type=_file_argument,
        metavar="PATH",
        help="index 명령의 JSON 결과에서 Source Unit을 일괄 게시",
    )
    publish.add_argument("--version", help="단건 게시 버전")
    publish.add_argument(
        "--allow-version-replacement",
        action="store_true",
        help=(
            "다른 게시 버전을 retired 처리하도록 명시 승인; "
            "배치 SHA 버전의 최신성은 자동 판별하지 않음"
        ),
    )
    publish.add_argument(
        "--collection-id", help="local default: published-guides; supabase: explicit approved ID"
    )

    search = cmd.add_parser("search", help="게시된 pgvector 자료를 검색")
    search.add_argument("query", metavar="QUERY")
    search.add_argument("--db-profile", choices=("local", "supabase"), default="local")
    search.add_argument("--top-k", type=int, default=3, help="검색 결과 수 1~10 (기본값: 3)")
    search.add_argument(
        "--collection-id", help="local default: published-guides; supabase: explicit approved ID"
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
        if args.db_profile == "supabase" and args.synthetic:
            parser.error("synthetic data is forbidden in Supabase operational collections")
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

        try:
            default_collection = (
                SOURCE_V2_TEST_COLLECTION if args.type == "source-v2" else DEFAULT_COLLECTION_ID
            )
            collection_id = _collection_for_profile(
                args.db_profile,
                args.collection_id
                if args.db_profile == "supabase"
                else args.collection_id or default_collection,
            )
        except DatabaseConfigurationError:
            print("approved RAG_COLLECTION_ID must match --collection-id", file=sys.stderr)
            return 2
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

                async def index_source():
                    if args.db_profile == "local":
                        return await index_source_v2(
                            args.path,
                            count_tokens=count_tokens,
                            collection_id=collection_id,
                        )
                    db = await _database_for_profile(args.db_profile)
                    try:
                        return await index_source_v2(
                            args.path,
                            count_tokens=count_tokens,
                            collection_id=collection_id,
                            database=db,
                        )
                    finally:
                        await _release_profile_database(db, args.db_profile)

                result = asyncio.run(index_source())
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

        if args.type == "mapped-xlsx":
            if not args.mapping or args.synthetic:
                parser.error("mapped-xlsx requires --mapping and rejects --synthetic")
            return _index_mapped_file(
                args.path,
                mapping_path=args.mapping,
                tokenizer_path=tokenizer_path,
                collection_id=collection_id,
                db_profile=args.db_profile,
            )

        if args.synthetic and "합성 시험 자료" not in args.source_title:
            parser.error("--synthetic 제목에는 '합성 시험 자료' 표시가 필요합니다")
        if args.synthetic and collection_id == DEFAULT_COLLECTION_ID:
            parser.error(
                "합성 시험자료는 기본 published-guides가 아닌 별도 collection에 적재해야 합니다"
            )
        index_arguments = {
            "tokenizer_path": tokenizer_path,
            "source_id": args.source_id,
            "version": args.version,
            "source_title": args.source_title,
            "source_url": args.source_url,
            "publisher": args.publisher,
            "collection_id": collection_id,
            "target_tokens": args.target_tokens,
            "is_synthetic": args.synthetic,
        }
        if args.db_profile == "local":
            return _index_file(args.path, **index_arguments)
        return _index_file(args.path, **index_arguments, db_profile=args.db_profile)
    if args.command == "publish":
        if args.from_index_result and args.version:
            parser.error("--from-index-result와 --version은 함께 사용할 수 없습니다")
        if args.source_id and not args.version:
            parser.error("단건 게시에는 --version이 필요합니다")
        if not args.source_id and args.version:
            parser.error("--version은 --source-id와 함께 사용해야 합니다")
        if args.source_id and args.allow_version_replacement:
            parser.error("--allow-version-replacement는 배치 게시에서만 사용할 수 있습니다")
        try:
            collection = _collection_for_profile(args.db_profile, args.collection_id)
        except DatabaseConfigurationError:
            print("approved RAG_COLLECTION_ID must match --collection-id", file=sys.stderr)
            return 2
        if args.from_index_result:
            return _publish_from_index_result(
                args.from_index_result,
                collection,
                args.db_profile,
                allow_version_replacement=args.allow_version_replacement,
            )
        if args.db_profile == "local":
            return _publish(args.source_id, args.version, collection)
        return _publish(args.source_id, args.version, collection, args.db_profile)
    if args.command == "search":
        if args.db_profile == "supabase" and args.allow_synthetic:
            parser.error("synthetic search not supported on Supabase")
        try:
            collection = _collection_for_profile(args.db_profile, args.collection_id)
        except DatabaseConfigurationError:
            return 2
        if args.db_profile == "local":
            return _search(args.query, args.top_k, collection, args.allow_synthetic)
        return _search(args.query, args.top_k, collection, args.allow_synthetic, args.db_profile)
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
