# 담당: [D] | 책임: 문서 파싱·청크·임베딩·적재 유스케이스.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-2, 6-1-3 (임베딩·저장 지원)
# 구현할 기능: 문서 버전별 적재와 Source_v2의 결정적 table_row 매핑을 수행한다.
# 완료 기준: 행을 검증한 뒤 명시적으로 색인하고 게시 전 자료를 검색에서 제외한다.
# 제한사항: 적재는 관리자 실행으로 제한하고 앱 시작 때 자동 실행하지 않는다.
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from starter_rag.ingestion.chunking import (
    DEFAULT_TARGET_TOKENS,
    DocumentChunk,
    chunk_document,
)
from starter_rag.ingestion.chunking_model import create_chunking_model_from_environment
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
) -> tuple[DocumentChunk, ...]:
    configured_model_factory = model_factory or create_chunking_model_from_environment
    model = configured_model_factory(environ)
    return await chunk_document(
        structure,
        source_id=source_id,
        version=version,
        model=model,
        count_tokens=count_tokens,
        target_tokens=target_tokens,
    )


SOURCE_V2_TEST_COLLECTION = "rag-test-source-v2-e2e"


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
    return "source-v2-" + _content_hash(unit)[:16]


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
        ("투입 조건", unit.condition),
        ("미확인·유의", unit.unverified),
        ("본문 범위", unit.scope),
        ("사용 주의", unit.caution),
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
    units: tuple[SourceUnit, ...],
    chunks: tuple[DocumentChunk, ...],
) -> dict[str, IndexedUnitRow]:
    """승인된 Source Unit마다 실제 Docling 표 행 하나를 연결한다.

    기존 청킹 알고리즘은 바꾸지 않는다. Source Unit 소유권과 안정 ID는 기존
    table-row 청킹이 끝난 뒤 부여한다.
    """
    candidates: dict[int, list[DocumentChunk]] = {}
    for chunk in chunks:
        if chunk.kind != "table_row" or chunk.table_row is None:
            raise SourceV2Error("Source_v2 input is not exclusively XLSX table-row chunks")
        candidates.setdefault(chunk.table_row.row_index, []).append(chunk)

    assigned: dict[str, IndexedUnitRow] = {}
    used_ids: set[str] = set()
    for unit in units:
        matching = [
            chunk
            for chunk in candidates.get(unit.row - 1, ())
            if _row_text_matches(unit, chunk.text)
        ]
        if len(matching) != 1:
            raise SourceV2Error(f"cannot identify exactly one verified XLSX row: {unit.source_id}")
        original = matching[0]
        if original.chunk_id in used_ids:
            raise SourceV2Error(f"same parsed chunk assigned twice: {unit.source_id}")
        if (
            original.generation_method != "deterministic"
            or original.model_status != "not_used"
            or original.fallback_used
            or original.model_attempts != 0
        ):
            raise SourceV2Error(f"non-deterministic row chunk: {unit.source_id}")
        used_ids.add(original.chunk_id)
        version = _version(unit)
        content_hash = _content_hash(unit)
        chunk_id = (
            "sha256:"
            + hashlib.sha256(
                f"{unit.source_id}:{version}:{original.content_sha256}:{content_hash}".encode()
            ).hexdigest()
        )
        assigned[unit.source_id] = IndexedUnitRow(
            chunk_id=chunk_id,
            source_id=unit.source_id,
            version=version,
            text=_searchable_row_text(unit),
            location=_location(unit, original),
            kind=original.kind,
            element_ids=original.element_ids,
            table_row=original.table_row,
        )
    return assigned


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
) -> dict[str, object]:
    """명시적으로 요청한 경우 원본 행 청킹과 768차원 임베딩을 격리 컬렉션에 색인한다."""
    if not re.fullmatch(r"[\w-]+", collection_id):
        raise SourceV2Error("safe collection ID is required")
    units, selected = await verify_source_rows(path, count_tokens=count_tokens)
    from starter_rag.contracts.models import DocumentVersion, SourceRef
    from starter_rag.embedding.model import EmbeddingGemma
    from starter_rag.storage.database import PostgresRagDatabase, database_url_from_environment
    from starter_rag.storage.vector_store import PGVectorStore

    # 31개 행 검증과 청크 소유권 확인이 끝나기 전에는 DB에 쓰지 않는다.
    db = PostgresRagDatabase(database_url_from_environment())
    try:
        vector_store = PGVectorStore(db, EmbeddingGemma(), collection_id=collection_id)
        outcomes = []
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
            outcome = await vector_store.index_document(doc_version, (row_chunk,))
            outcomes.append(
                {
                    "source_id": unit.source_id,
                    "chunk_id": row_chunk.chunk_id,
                    "version": row_chunk.version,
                    "chunk_kind": row_chunk.kind,
                    "indexed_state": outcome.state,
                    "skipped": outcome.skipped,
                }
            )
        return {
            "indexed_units": len(outcomes),
            "collection_id": collection_id,
            "chunks": len(outcomes),
            "outcomes": outcomes,
            "published": False,
        }
    finally:
        await db.close()
