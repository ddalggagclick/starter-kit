# 담당: [D] | 책임: 문서 파싱·청크·임베딩·적재 유스케이스.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-2, 6-1-3 (임베딩·저장 지원)
# 구현할 기능: 문서 버전별 적재와 Source_v2의 결정적 table_row 매핑을 수행한다.
# 완료 기준: 행을 검증한 뒤 명시적으로 색인하고 게시 전 자료를 검색에서 제외한다.
# 제한사항: 적재는 관리자 실행으로 제한하고 앱 시작 때 자동 실행하지 않는다.
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.language_models.chat_models import BaseChatModel

if TYPE_CHECKING:
    from starter_rag.contracts.models import DocumentVersion
    from starter_rag.contracts.ports import EmbeddingPort
    from starter_rag.storage.database import PostgresRagDatabase
    from starter_rag.storage.vector_store import IndexOutcome

from starter_rag.ingestion.chunking import (
    DEFAULT_PROMPT_TOKEN_BUDGET,
    DEFAULT_TARGET_TOKENS,
    DocumentChunk,
    chunk_document,
)
from starter_rag.ingestion.chunking_model import create_chunking_model_from_environment
from starter_rag.ingestion.errors import ProjectionError
from starter_rag.ingestion.parser import (
    DocumentStructure,
    SourceUnit,
    SourceV2Error,
    extract_document_structure,
    parse_document,
    read_source_units,
)


async def chunk_document_with_config(
    structure: DocumentStructure,
    *,
    source_id: str,
    version: str,
    count_tokens: Callable[[str], int],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    environ: Mapping[str, str] | None = None,
    model_factory: Callable[[Mapping[str, str] | None], BaseChatModel] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[DocumentChunk, ...]:
    configured_model_factory = model_factory or create_chunking_model_from_environment
    model = configured_model_factory(environ)
    values = os.environ if environ is None else environ
    try:
        context_tokens = int(values.get("RAG_CHUNKING_CONTEXT_TOKENS", "4096"))
        reserve_tokens = int(values.get("RAG_CHUNKING_RESPONSE_RESERVE_TOKENS", "1024"))
    except ValueError:
        raise ValueError("RAG 청킹 컨텍스트와 응답 예산은 정수여야 합니다.") from None
    if context_tokens <= 0 or reserve_tokens < 0 or reserve_tokens >= context_tokens:
        raise ValueError("RAG 청킹 컨텍스트는 응답 예산보다 커야 합니다.")
    prompt_token_budget = context_tokens - reserve_tokens
    if (
        "RAG_CHUNKING_CONTEXT_TOKENS" not in values
        and "RAG_CHUNKING_RESPONSE_RESERVE_TOKENS" not in values
    ):
        prompt_token_budget = DEFAULT_PROMPT_TOKEN_BUDGET
    return await chunk_document(
        structure,
        source_id=source_id,
        version=version,
        model=model,
        count_tokens=count_tokens,
        target_tokens=target_tokens,
        prompt_token_budget=prompt_token_budget,
        progress=progress,
    )


# Existing dataset adapter remains for CLI compatibility; generic projection is below.
SOURCE_V2_TEST_COLLECTION = "rag-test-source-v2-e2e"


@dataclass(frozen=True)
class RowProjectionSpec:
    id_field: str
    row_field: str
    excerpt_field: str
    internal_url_field: str
    display_url_field: str
    hash_fields: tuple[tuple[str, str], ...]  # (serialized key, input field)
    searchable_fields: tuple[tuple[str, str], ...]  # (display label, input field)
    location_fields: tuple[tuple[str, str], ...]  # (output key, input field)
    location_constants: tuple[tuple[str, Any], ...]
    location_row_index_key: str
    location_provenance_key: str
    version_prefix: str
    version_digest_length: int = 16

    def __post_init__(self) -> None:
        required_strings = (
            self.id_field,
            self.row_field,
            self.excerpt_field,
            self.internal_url_field,
            self.display_url_field,
            self.location_row_index_key,
            self.location_provenance_key,
            self.version_prefix,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required_strings):
            raise ProjectionError("projection field names and version prefix are required")
        if (
            isinstance(self.version_digest_length, bool)
            or not isinstance(self.version_digest_length, int)
            or not 1 <= self.version_digest_length <= 64
        ):
            raise ProjectionError("version digest length must be within 1..64")
        _validate_projection_pairs(self.hash_fields, "hash_fields")
        _validate_projection_pairs(self.searchable_fields, "searchable_fields")
        _validate_projection_pairs(self.location_fields, "location_fields")
        _validate_projection_pairs(
            self.location_constants, "location_constants", values=False, allow_empty=True
        )
        location_keys = [key for key, _ in self.location_fields]
        location_keys.extend(key for key, _ in self.location_constants)
        location_keys.extend((self.location_row_index_key, self.location_provenance_key))
        if len(location_keys) != len(set(location_keys)):
            raise ProjectionError("location projection keys must be unique")


def _validate_projection_pairs(
    value: object,
    name: str,
    *,
    values: bool = True,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, tuple) or (not value and not allow_empty):
        raise ProjectionError(f"{name} must contain pairs")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ProjectionError(f"{name} must contain key/value pairs")
        key, field = item
        if not isinstance(key, str) or not key.strip():
            raise ProjectionError(f"{name} keys must be non-empty strings")
        if values and (not isinstance(field, str) or not field.strip()):
            raise ProjectionError(f"{name} field names must be non-empty strings")
    keys = [item[0] for item in value]
    if len(keys) != len(set(keys)):
        raise ProjectionError(f"{name} keys must be unique")


@dataclass(frozen=True)
class ProjectedChunk:
    chunk_id: str
    source_id: str
    version: str
    text: str
    location: str
    kind: str
    element_ids: tuple[str, ...]
    table_row: object


def content_hash(record: Mapping[str, Any], spec: RowProjectionSpec) -> str:
    payload = {output_key: record[input_key] for output_key, input_key in spec.hash_fields}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def version_for(record: Mapping[str, Any], spec: RowProjectionSpec) -> str:
    return spec.version_prefix + content_hash(record, spec)[: spec.version_digest_length]


def searchable_text(record: Mapping[str, Any], spec: RowProjectionSpec) -> str:
    text = "\n".join(
        f"{label}: {record[field]}"
        for label, field in spec.searchable_fields
        if record[field].strip()
    )
    private_url = record[spec.internal_url_field]
    if private_url and not record[spec.display_url_field] and private_url in text:
        raise ProjectionError(f"hidden URL in indexed text: {record[spec.id_field]}")
    return text


def location_for(record: Mapping[str, Any], parsed_chunk: object, spec: RowProjectionSpec) -> str:
    raw_locations = parsed_chunk.locations
    provenance = [asdict(loc) if is_dataclass(loc) else dict(loc) for loc in raw_locations]
    payload = {key: record[field] for key, field in spec.location_fields}
    payload.update(dict(spec.location_constants))
    payload[spec.location_row_index_key] = parsed_chunk.table_row.row_index
    payload[spec.location_provenance_key] = provenance
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def project_verified_rows(
    records: Sequence[Mapping[str, Any]],
    parsed_chunks: Sequence[object],
    spec: RowProjectionSpec,
) -> dict[str, ProjectedChunk]:
    """Project validated input records to deterministic, single-table-row chunks.

    Parsing and dataset-specific approval rules are deliberately out of scope.
    """
    try:
        return _project_verified_rows(records, parsed_chunks, spec)
    except ProjectionError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise ProjectionError("projection input does not match its configured schema") from error


def _project_verified_rows(
    records: Sequence[Mapping[str, Any]],
    parsed_chunks: Sequence[object],
    spec: RowProjectionSpec,
) -> dict[str, ProjectedChunk]:
    candidates: dict[int, list[object]] = {}
    parsed_chunk_ids: set[str] = set()
    for chunk in parsed_chunks:
        table_row = getattr(chunk, "table_row", None)
        row_index = getattr(table_row, "row_index", None)
        if (
            getattr(chunk, "kind", None) != "table_row"
            or isinstance(row_index, bool)
            or not isinstance(row_index, int)
            or row_index < 0
        ):
            raise ProjectionError("only parsed table rows with valid row positions are accepted")
        _validate_deterministic_chunk(chunk)
        if chunk.chunk_id in parsed_chunk_ids:
            raise ProjectionError("parsed table row chunk IDs must be unique")
        parsed_chunk_ids.add(chunk.chunk_id)
        candidates.setdefault(row_index, []).append(chunk)

    result: dict[str, ProjectedChunk] = {}
    used_ids: set[str] = set()
    for record in records:
        source_id = record[spec.id_field]
        row_number = record[spec.row_field]
        excerpt = record[spec.excerpt_field]
        internal_url = record[spec.internal_url_field]
        display_url = record[spec.display_url_field]
        if not isinstance(source_id, str) or not source_id.strip():
            raise ProjectionError("source IDs must be non-empty strings")
        if isinstance(row_number, bool) or not isinstance(row_number, int) or row_number < 1:
            raise ProjectionError(f"invalid worksheet row for source: {source_id}")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ProjectionError(f"source excerpt is required: {source_id}")
        if display_url not in (True, False) or not isinstance(display_url, bool):
            raise ProjectionError(f"display URL policy must be boolean: {source_id}")
        if internal_url is not None and not isinstance(internal_url, str):
            raise ProjectionError(f"source URL must be text or null: {source_id}")
        if display_url and not internal_url:
            raise ProjectionError("a displayed source URL must exist")

        matches = [
            chunk
            for chunk in candidates.get(row_number - 1, ())
            if source_id in chunk.text
            and _normalize_row_text(excerpt) in _normalize_row_text(chunk.text)
        ]
        if len(matches) != 1:
            raise ProjectionError(f"ambiguous or missing parsed row: {source_id}")
        parsed = matches[0]
        if source_id in result or parsed.chunk_id in used_ids:
            raise ProjectionError(f"duplicate row assignment: {source_id}")
        used_ids.add(parsed.chunk_id)
        digest = content_hash(record, spec)
        version = version_for(record, spec)
        chunk_id = (
            "sha256:"
            + hashlib.sha256(
                f"{source_id}:{version}:{parsed.content_sha256}:{digest}".encode()
            ).hexdigest()
        )
        result[source_id] = ProjectedChunk(
            chunk_id=chunk_id,
            source_id=source_id,
            version=version,
            text=searchable_text(record, spec),
            location=location_for(record, parsed, spec),
            kind=parsed.kind,
            element_ids=parsed.element_ids,
            table_row=parsed.table_row,
        )
    return result


def _validate_deterministic_chunk(chunk: object) -> None:
    chunk_id = getattr(chunk, "chunk_id", None)
    text = getattr(chunk, "text", None)
    content_digest = getattr(chunk, "content_sha256", None)
    model_attempts = getattr(chunk, "model_attempts", None)
    if (
        not isinstance(chunk_id, str)
        or not chunk_id.strip()
        or not isinstance(text, str)
        or not text.strip()
        or not isinstance(content_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", content_digest) is None
        or getattr(chunk, "generation_method", None) != "deterministic"
        or getattr(chunk, "model_status", None) != "not_used"
        or getattr(chunk, "fallback_used", None) is not False
        or isinstance(model_attempts, bool)
        or not isinstance(model_attempts, int)
        or model_attempts != 0
        or not isinstance(getattr(chunk, "element_ids", None), tuple)
        or not chunk.element_ids
        or not isinstance(getattr(chunk, "locations", None), tuple)
    ):
        raise ProjectionError("parsed table row must be a valid deterministic chunk")


def _normalize_row_text(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True)
class IndexedUnitRow:
    """실제 Docling table_row와 정확한 출처 표기를 보존하는 청크 어댑터."""

    chunk_id: str
    source_id: str
    version: str
    text: str
    location: str
    kind: str
    element_ids: tuple[str, ...]
    table_row: object


_LEGACY_PROJECTION = RowProjectionSpec(
    id_field="source_id",
    row_field="row",
    excerpt_field="excerpt",
    internal_url_field="official_url",
    display_url_field="display_link_allowed",
    hash_fields=(
        ("source_id", "source_id"),
        ("title", "title"),
        ("publisher", "publisher"),
        ("excerpt", "excerpt"),
        ("condition", "condition"),
        ("unverified", "unverified"),
        ("scope", "scope"),
        ("caution", "caution"),
        ("official_url", "official_url"),
        ("display_link_allowed", "display_link_allowed"),
        ("official_location_note", "official_location_note"),
        ("version_note", "version_note"),
        ("xlsx_row", "row"),
        ("historical_positions", "historical_positions"),
    ),
    searchable_fields=(
        ("Source Unit", "source_id"),
        ("절차·주제", "title"),
        ("확인한 내용·유의 (인용 발췌)", "excerpt"),
    ),
    location_fields=(
        ("source_unit_id", "source_id"),
        ("source_v2_row", "row"),
        ("historical_excerpt_positions", "historical_positions"),
        ("official_location_note", "official_location_note"),
    ),
    location_constants=(
        ("source_v2_sheet", "RAG_Unit본문"),
        ("chunk_kind", "table_row"),
        ("historical_positions_are_live_links", False),
        ("official_location_verified", False),
    ),
    location_row_index_key="chunk_row_index",
    location_provenance_key="docling_locations",
    # 원본 해시는 유지하되 검색 본문 형식 변경은 새 문서 버전으로 구분한다.
    version_prefix="source-v2-text-v2-",
)


def _content_hash(unit: SourceUnit) -> str:
    """검색 결과에 영향을 주는 표시·출처 정보까지 포함해 버전을 만든다."""
    payload = {
        "source_id": unit.source_id,
        "title": unit.title,
        "publisher": unit.publisher,
        "excerpt": unit.excerpt,
        "condition": unit.condition,
        "unverified": unit.unverified,
        "scope": unit.scope,
        "caution": unit.caution,
        "official_url": unit.official_url,
        "display_link_allowed": unit.display_link_allowed,
        "official_location_note": unit.official_location_note,
        "version_note": unit.version_note,
        "xlsx_row": unit.row,
        "historical_positions": unit.historical_positions,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _version(unit: SourceUnit) -> str:
    return _LEGACY_PROJECTION.version_prefix + _content_hash(unit)[:16]


def _location(unit: SourceUnit, original_row: object) -> str:
    """통합문서 행, 과거 H셀 참조, 공식 페이지 위치를 구분해 기록한다."""
    from dataclasses import asdict

    values = {
        "source_unit_id": unit.source_id,
        "source_v2_sheet": "RAG_Unit본문",
        "source_v2_row": unit.row,
        "chunk_kind": "table_row",
        "chunk_row_index": original_row.table_row.row_index,
        "historical_excerpt_positions": list(unit.historical_positions),
        "historical_positions_are_live_links": False,
        "official_location_note": unit.official_location_note,
        "official_location_verified": False,
        "docling_locations": [asdict(item) for item in original_row.locations],
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _searchable_row_text(unit: SourceUnit) -> str:
    """내부 URL 열을 제외하고 정리된 발췌문만 검색 본문에 포함한다."""
    fields = (
        ("Source Unit", unit.source_id),
        ("절차·주제", unit.title),
        ("확인한 내용·유의 (인용 발췌)", unit.excerpt),
    )
    text = "\n".join(f"{label}: {value}" for label, value in fields if value.strip())
    if unit.official_url and not unit.display_link_allowed and unit.official_url in text:
        raise SourceV2Error(f"hidden URL would be included in search text: {unit.source_id}")
    return text


def _row_text_matches(unit: SourceUnit, text: str) -> bool:
    """정리된 출처 ID와 원문 발췌가 모두 일치하는 행만 찾는다."""
    normalized = lambda value: " ".join(value.split())
    return unit.source_id in text and normalized(unit.excerpt) in normalized(text)


def assign_source_rows(
    units: tuple[SourceUnit, ...], chunks: tuple[DocumentChunk, ...]
) -> dict[str, IndexedUnitRow]:
    """Compatibility adapter: dataset validation stays outside the generic projector."""
    try:
        rows = project_verified_rows([asdict(unit) for unit in units], chunks, _LEGACY_PROJECTION)
    except ProjectionError as exc:
        raise SourceV2Error(str(exc)) from exc
    return {
        source_id: IndexedUnitRow(
            row.chunk_id,
            row.source_id,
            row.version,
            row.text,
            row.location,
            row.kind,
            row.element_ids,
            row.table_row,
        )
        for source_id, row in rows.items()
    }


async def verify_source_rows(
    path: str | Path, *, count_tokens: Callable[[str], int]
) -> tuple[tuple[SourceUnit, ...], dict[str, IndexedUnitRow]]:
    """실제 Docling과 기존 table-row 청커로 확인하되 DB에는 쓰지 않는다."""
    path = Path(path)
    units = read_source_units(path)
    document = parse_document(path)
    structure = extract_document_structure(document, path)
    if structure.source_format != "xlsx" or any(x.kind != "table" for x in structure.elements):
        raise SourceV2Error("the Source_v2 Docling structure must be XLSX tables only")
    chunks = await chunk_document_with_config(
        structure,
        source_id="source-v2-worksheet",
        version="source-v2-table",
        count_tokens=count_tokens,
    )
    selected = assign_source_rows(units, chunks)
    return units, selected


async def index_source_v2(
    path: str | Path,
    *,
    count_tokens: Callable[[str], int],
    collection_id: str = SOURCE_V2_TEST_COLLECTION,
    database: PostgresRagDatabase | None = None,
) -> dict[str, object]:
    """명시적으로 요청한 경우 원본 행 청킹과 768차원 임베딩을 격리 컬렉션에 색인한다."""
    if not re.fullmatch(r"[\w-]+", collection_id):
        raise SourceV2Error("safe collection ID is required")
    units, selected = await verify_source_rows(path, count_tokens=count_tokens)
    from starter_rag.contracts.models import DocumentVersion, SourceRef
    from starter_rag.storage.database import PostgresRagDatabase, database_url_from_environment

    # 31개 행 검증과 청크 소유권 확인이 끝나기 전에는 DB에 쓰지 않는다.
    db = database if database is not None else PostgresRagDatabase(database_url_from_environment())
    try:
        documents = []
        prepared = []
        for unit in units:
            row_chunk = selected[unit.source_id]
            source = SourceRef(
                source_id=unit.source_id,
                title=unit.title,
                url=unit.official_url if unit.display_link_allowed else None,
                publisher=unit.publisher,
                version=row_chunk.version,
            )
            doc_version = DocumentVersion(
                source=source,
                content_sha256=_content_hash(unit),
                state="staging",
                chunk_count=1,
            )
            documents.append((doc_version, (row_chunk,)))
            prepared.append(
                {
                    "source_id": unit.source_id,
                    "chunk_id": row_chunk.chunk_id,
                    "version": row_chunk.version,
                    "chunk_kind": row_chunk.kind,
                    "indexed_state": "indexed",
                    "skipped": False,
                }
            )
        indexed = await index_documents(documents, database=db, collection_id=collection_id)
        outcomes = [
            {**item, "indexed_state": result.state, "skipped": result.skipped}
            for item, result in zip(prepared, indexed, strict=True)
        ]
        return {
            "indexed_units": len(outcomes),
            "collection_id": collection_id,
            "chunks": len(outcomes),
            "outcomes": outcomes,
            "published": False,
        }
    finally:
        if database is None:
            await db.close()


async def index_documents(
    documents: Sequence[tuple[DocumentVersion, tuple[object, ...]]],
    *,
    database: PostgresRagDatabase,
    collection_id: str,
    embedding: EmbeddingPort | None = None,
) -> tuple[IndexOutcome, ...]:
    """Use the same VectorPort implementation for local and caller-owned PostgreSQL.

    Parsing and dataset approval are upstream; only indexed state is produced.
    Caller owns the database and publication remains an explicit separate step.
    """
    from starter_rag.embedding.model import EmbeddingGemma
    from starter_rag.storage.vector_store import PGVectorStore

    if not collection_id.strip():
        raise ValueError("collection_id is required")
    store = PGVectorStore(database, embedding or EmbeddingGemma(), collection_id=collection_id)
    outcomes = []
    for document, chunks in documents:
        if not chunks or len(chunks) != document.chunk_count:
            raise ValueError("document chunk_count does not match validated input")
        outcomes.append(await store.index_document(document, chunks))
    return tuple(outcomes)


def read_mapped_xlsx(
    path: str | Path, mapping: Mapping[str, object]
) -> tuple[dict[str, object], ...]:
    """Read any single worksheet using caller-supplied header mappings, no fixed domain IDs."""
    from starter_rag.ingestion.parser import read_xlsx_table_rows

    sheet = mapping.get("sheet")
    fields = mapping.get("fields")
    if not isinstance(sheet, str) or not sheet or not isinstance(fields, dict):
        raise ValueError("mapping requires sheet and fields")
    if not all(isinstance(k, str) and isinstance(v, str) and v for k, v in fields.items()):
        raise ValueError("mapping field names must be non-empty strings")
    rows = read_xlsx_table_rows(Path(path), sheet)
    if not rows or rows[0][0] != 1:
        raise ValueError("missing first header row")
    headers = {text.strip(): col for col, text in rows[0][1].items() if text.strip()}
    if len(headers) != sum(bool(x.strip()) for x in rows[0][1].values()):
        raise ValueError("duplicate XLSX headers")
    if any(label not in headers for label in fields.values()):
        raise ValueError("mapping headers are missing")
    approval = mapping.get("approval")
    if approval is not None and (
        not isinstance(approval, dict)
        or not isinstance(approval.get("field"), str)
        or not isinstance(approval.get("value"), str)
    ):
        raise ValueError("approval must specify field and value")
    if approval is not None and approval["field"] not in fields:
        raise ValueError("approval field must be mapped")
    records = []
    seen = set()
    for row_number, cells in rows[1:]:
        record: dict[str, object] = {
            name: cells.get(headers[label], "") for name, label in fields.items()
        }
        if not any(record.values()):
            continue
        if approval is not None and record[approval["field"]] != approval["value"]:
            raise ValueError(f"row {row_number} is not approved")
        for name in ("source_id", "title", "publisher", "official_url", "display_link_allowed"):
            if isinstance(record.get(name), str):
                record[name] = record[name].strip()
        record["row"] = row_number
        for name in mapping.get("nullable_fields", ()):
            if name in record and record[name] == "":
                record[name] = None
        for name, rule in mapping.get("boolean_fields", {}).items():
            if not isinstance(rule, dict) or record.get(name) not in rule:
                raise ValueError(f"row {row_number}: invalid boolean field {name}")
            record[name] = bool(rule[record[name]])
        for name, separator in mapping.get("split_fields", {}).items():
            if not isinstance(separator, str) or not separator:
                raise ValueError("split separator must not be empty")
            record[name] = tuple(
                part.strip() for part in str(record[name]).split(separator) if part.strip()
            )
        sid = record.get("source_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError(f"row {row_number}: missing or duplicate source_id")
        seen.add(sid)
        if not all(record.get(name) for name in ("title", "publisher", "excerpt")):
            raise ValueError(f"row {row_number}: missing title, publisher or excerpt")
        records.append(record)
    if not records:
        raise ValueError("no approved source records")
    return tuple(records)


def projection_from_mapping(mapping: Mapping[str, object]) -> RowProjectionSpec:
    """Build a stable projection from data, not Python per-domain conditionals."""
    fields = mapping.get("projection")
    if not isinstance(fields, dict):
        raise ValueError("projection configuration is required")  # noqa: TRY004
    required = {
        "id_field",
        "row_field",
        "excerpt_field",
        "internal_url_field",
        "display_url_field",
        "hash_fields",
        "searchable_fields",
        "location_fields",
        "location_constants",
        "location_row_index_key",
        "location_provenance_key",
        "version_prefix",
    }
    if not required.issubset(fields):
        raise ValueError("projection configuration is incomplete")
    try:
        return RowProjectionSpec(
            **{
                name: tuple(tuple(x) for x in value)
                if name
                in ("hash_fields", "searchable_fields", "location_fields", "location_constants")
                else value
                for name, value in fields.items()
            }
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid projection configuration") from exc


async def verify_mapped_xlsx(
    path: str | Path,
    mapping: Mapping[str, object],
    *,
    count_tokens: Callable[[str], int],
) -> tuple[tuple[dict[str, object], ...], dict[str, ProjectedChunk]]:
    """Validate input and deterministic Docling rows without database writes."""
    records = read_mapped_xlsx(path, mapping)
    spec = projection_from_mapping(mapping)
    source_path = Path(path)
    document = parse_document(source_path)
    structure = extract_document_structure(document, source_path)
    if structure.source_format != "xlsx" or any(
        element.kind != "table" for element in structure.elements
    ):
        raise ProjectionError("mapped XLSX must contain table elements only")
    docling_config = mapping.get("docling")
    if not isinstance(docling_config, dict) or not all(
        isinstance(docling_config.get(name), str) and docling_config[name]
        for name in ("source_id", "version")
    ):
        raise ProjectionError("docling source ID and version must be configured")
    chunks = await chunk_document_with_config(
        structure,
        source_id=docling_config["source_id"],
        version=docling_config["version"],
        count_tokens=count_tokens,
    )
    return records, project_verified_rows(records, chunks, spec)


async def index_mapped_xlsx(
    path: str | Path,
    mapping: Mapping[str, object],
    *,
    count_tokens: Callable[[str], int],
    database: PostgresRagDatabase,
    collection_id: str,
) -> dict[str, object]:
    """Index a caller-mapped document dataset into any prevalidated PostgreSQL target."""
    from starter_rag.contracts.models import DocumentVersion, SourceRef

    records, projected = await verify_mapped_xlsx(path, mapping, count_tokens=count_tokens)
    spec = projection_from_mapping(mapping)
    documents = []
    for record in records:
        source_id = record[spec.id_field]
        chunk = projected[source_id]
        url = record[spec.internal_url_field] if record[spec.display_url_field] else None
        source = SourceRef(
            source_id=source_id,
            title=record["title"],
            url=url,
            publisher=record["publisher"],
            version=chunk.version,
        )
        documents.append(
            (
                DocumentVersion(
                    source=source,
                    content_sha256=content_hash(record, spec),
                    state="staging",
                    chunk_count=1,
                ),
                (chunk,),
            )
        )
    indexed = await index_documents(documents, database=database, collection_id=collection_id)
    return {
        "indexed_units": len(indexed),
        "collection_id": collection_id,
        "chunks": len(indexed),
        "outcomes": [
            {
                "source_id": result.source_id,
                "chunk_id": projected[result.source_id].chunk_id,
                "version": result.version,
                "chunk_kind": "table_row",
                "indexed_state": result.state,
                "skipped": result.skipped,
            }
            for result in indexed
        ],
        "published": False,
    }
