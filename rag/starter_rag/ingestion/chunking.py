# 담당: [D] | 책임: 문서 구조와 출처 위치를 보존하는 청크 생성.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-1, 6-1-2 (파싱·임베딩 지원)
# 구현할 기능: 일반 문서는 인접 요소를 그룹화하고, 표는 행별 청크를 생성한다.
# 완료 기준: 원문 구조·위치·해시를 보존하고 표 행을 하나씩 복원할 수 있다.
# 제한사항: 앱 시작 시 청킹이나 색인을 자동 실행하지 않는다.
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from starter_rag.ingestion.parser import (
    DocumentBoundingBox,
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    TableCellStructure,
    TableStructure,
)

ChunkKind = Literal["document", "table_row"]
GenerationMethod = Literal["agentic", "deterministic"]
ModelStatus = Literal["succeeded", "failed", "not_used"]
MAX_MODEL_ATTEMPTS = 4
DEFAULT_TARGET_TOKENS = 512


@dataclass(frozen=True)
class TableCellUse:
    # 한 행이 소유하는 셀 또는 앞선 행의 병합 셀을 가리킨다.

    cell_index: int
    relation: Literal["source", "merged_reference"]
    cell: TableCellStructure | None
    start_row: int
    end_row: int
    start_column: int
    end_column: int
    row_span: int
    column_span: int
    column_header: bool
    row_header: bool
    row_section: bool
    fillable: bool
    self_ref: str | None
    bbox: DocumentBoundingBox | None


@dataclass(frozen=True)
class TableRowChunkMetadata:
    # 행 청크에 필요한 표 구조와 원본 행 검증 정보를 담는다.

    table_id: str
    row_id: str
    row_index: int
    row_count: int
    column_count: int
    cells: tuple[TableCellUse, ...]
    header_cell_indexes: tuple[int, ...]
    is_header: bool
    original_row_sha256: str
    completeness_status: Literal["unverified"]


@dataclass(frozen=True)
class DocumentChunk:
    # 공개 ChunkRecord와 분리된 청킹 단계의 내부 결과.

    chunk_id: str
    source_id: str
    version: str
    kind: ChunkKind
    element_ids: tuple[str, ...]
    text: str
    source_elements: tuple[DocumentElement, ...]
    table_id: str | None
    table_row: TableRowChunkMetadata | None
    token_count: int
    over_target: bool
    content_sha256: str
    generation_method: GenerationMethod
    model_status: ModelStatus
    model_attempts: int
    model_failure: str | None
    fallback_used: bool

    @property
    def locations(self) -> tuple[DocumentLocation, ...]:
        # 원본 DTO를 참조해 그룹 또는 표 행의 위치와 provenance를 돌려준다.
        return tuple(element.location for element in self.source_elements)

    @property
    def original_texts(self) -> tuple[str | None, ...]:
        # Parser가 제공한 original_text를 수정 없이 노출한다.
        return tuple(element.original_text for element in self.source_elements)


class ChunkingError(ValueError):
    # 청킹 입력·출력의 무결성을 확인할 수 없다.
    pass


class ChunkIntegrityError(ChunkingError):
    # 요소, 행, 셀 또는 원문 순서가 일치하지 않는다.
    pass


class UnresolvedCellTextError(ChunkIntegrityError):
    # 표 DTO가 셀의 실제 원문 텍스트를 제공하지 않는다.
    pass


class InvalidTokenCountError(ChunkingError):
    # 외부 주입 토큰 계산기가 유효하지 않은 값을 반환했다.
    pass


class ChunkGroupingResponseError(ChunkingError):
    # LLM 응답이 그룹 JSON 또는 그룹핑 규칙을 충족하지 않는다.
    pass


@dataclass(frozen=True)
class _ElementRef:
    element_id: str
    position: int
    element: DocumentElement
    text: str
    segment_index: int


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _element_id(position: int) -> str:
    return f"e{position + 1:06d}"


def _row_id(table_id: str, row_index: int) -> str:
    return f"{table_id}:r{row_index + 1:06d}"


def _validate_structure(structure: DocumentStructure) -> tuple[tuple[_ElementRef, ...], ...]:
    # DTO 순서와 표 좌표를 확인하고 일반 문서 요소의 연속 구간을 돌려준다.
    segments: list[list[_ElementRef]] = []
    current: list[_ElementRef] = []

    for position, element in enumerate(structure.elements):
        if element.kind == "table":
            if current:
                segments.append(current)
                current = []
            if element.table is None:
                raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
            _validate_table(element.table)
            continue
        if element.kind not in {"document_title", "section_title", "paragraph"}:
            raise ChunkIntegrityError(f"지원하지 않는 문서 요소 종류입니다: {element.kind}")
        if not isinstance(element.text, str):
            raise ChunkIntegrityError("일반 문서 요소에 원문 텍스트가 없습니다.")
        current.append(
            _ElementRef(
                element_id=_element_id(position),
                position=position,
                element=element,
                text=element.text,
                segment_index=len(segments),
            )
        )

    if current:
        segments.append(current)
    return tuple(tuple(segment) for segment in segments)


def _validate_table(table: TableStructure) -> None:
    if table.row_count <= 0:
        raise ChunkIntegrityError("표의 row_count는 0보다 커야 합니다.")
    if table.column_count <= 0:
        raise ChunkIntegrityError("표의 column_count는 0보다 커야 합니다.")
    if len(table.rows) != table.row_count:
        raise ChunkIntegrityError("표 행 DTO 개수가 row_count와 다릅니다.")

    for expected_row_index, row in enumerate(table.rows):
        if row.row_index != expected_row_index:
            raise ChunkIntegrityError("표 행 인덱스가 원본 순서와 다릅니다.")

    expected_start_indexes: list[list[int]] = [[] for _ in range(table.row_count)]
    occupied_cells: dict[tuple[int, int], int] = {}
    for cell_index, cell in enumerate(table.cells):
        if not isinstance(cell.text, str):
            raise UnresolvedCellTextError(f"표 셀 {cell_index}의 원문 텍스트를 확인할 수 없습니다.")
        if not (
            0 <= cell.start_row < cell.end_row <= table.row_count
            and 0 <= cell.start_column < cell.end_column <= table.column_count
            and cell.row_span > 0
            and cell.column_span > 0
        ):
            raise ChunkIntegrityError(
                f"표 셀 {cell_index}의 병합 범위가 유효하지 않습니다: "
                f"행 [{cell.start_row}, {cell.end_row}), "
                f"열 [{cell.start_column}, {cell.end_column})"
            )
        actual_row_span = cell.end_row - cell.start_row
        if cell.row_span != actual_row_span:
            raise ChunkIntegrityError(
                f"표 셀 {cell_index}의 row_span({cell.row_span})이 "
                f"행 범위({actual_row_span})와 다릅니다."
            )
        actual_column_span = cell.end_column - cell.start_column
        if cell.column_span != actual_column_span:
            raise ChunkIntegrityError(
                f"표 셀 {cell_index}의 column_span({cell.column_span})이 "
                f"열 범위({actual_column_span})와 다릅니다."
            )

        for row_index in range(cell.start_row, cell.end_row):
            for column_index in range(cell.start_column, cell.end_column):
                coordinate = (row_index, column_index)
                previous_cell_index = occupied_cells.get(coordinate)
                if previous_cell_index is not None:
                    raise ChunkIntegrityError(
                        f"표 셀 {cell_index}와 셀 {previous_cell_index}가 "
                        f"격자 위치 {coordinate}를 중복 점유합니다."
                    )
                occupied_cells[coordinate] = cell_index
        expected_start_indexes[cell.start_row].append(cell_index)

    for row_index, row in enumerate(table.rows):
        if row.cell_indexes != tuple(expected_start_indexes[row_index]):
            raise ChunkIntegrityError(f"표 {row_index}행의 cell_indexes가 시작 셀 목록과 다릅니다.")


def _all_element_ids(structure: DocumentStructure) -> dict[str, tuple[int, DocumentElement]]:
    return {
        _element_id(position): (position, element)
        for position, element in enumerate(structure.elements)
    }


def _validate_token_count(count_tokens: Callable[[str], int], text: str) -> int:
    try:
        count = count_tokens(text)
    except Exception as error:
        raise InvalidTokenCountError("토큰 계산기가 토큰 수를 계산하지 못했습니다.") from error
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise InvalidTokenCountError("토큰 계산기는 0 이상의 정수를 반환해야 합니다.")
    return count


def _join_element_text(refs: Sequence[_ElementRef]) -> str:
    # 검색 텍스트에서 요소 경계를 표시하며 각 원문 문자열은 그대로 둔다.
    return "\n".join(ref.text for ref in refs)


def _document_content_hash(elements: Sequence[DocumentElement], text: str) -> str:
    return _digest(
        {
            "source_texts": [
                {"text": element.text, "original_text": element.original_text}
                for element in elements
            ],
            "search_text": text,
        }
    )


def _row_source_cells(
    table: TableStructure, row_index: int
) -> tuple[tuple[int, TableCellStructure], ...]:
    return tuple(
        (cell_index, cell)
        for cell_index, cell in enumerate(table.cells)
        if cell.start_row == row_index
    )


def _table_row_metadata(
    table_element: DocumentElement,
    table_id: str,
    row_index: int,
) -> TableRowChunkMetadata:
    table = table_element.table
    if table is None:
        raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")

    covered_cells = sorted(
        (
            (cell_index, cell)
            for cell_index, cell in enumerate(table.cells)
            if cell.start_row <= row_index < cell.end_row
        ),
        key=lambda pair: (pair[1].start_column, pair[1].end_column, pair[0]),
    )
    uses = tuple(
        TableCellUse(
            cell_index=cell_index,
            relation="source" if cell.start_row == row_index else "merged_reference",
            cell=cell if cell.start_row == row_index else None,
            start_row=cell.start_row,
            end_row=cell.end_row,
            start_column=cell.start_column,
            end_column=cell.end_column,
            row_span=cell.row_span,
            column_span=cell.column_span,
            column_header=cell.column_header,
            row_header=cell.row_header,
            row_section=cell.row_section,
            fillable=cell.fillable,
            self_ref=cell.self_ref,
            bbox=cell.bbox,
        )
        for cell_index, cell in covered_cells
    )
    header_indexes = tuple(
        cell_index for cell_index, cell in enumerate(table.cells) if cell.column_header
    )
    return TableRowChunkMetadata(
        table_id=table_id,
        row_id=_row_id(table_id, row_index),
        row_index=row_index,
        row_count=table.row_count,
        column_count=table.column_count,
        cells=uses,
        header_cell_indexes=header_indexes,
        is_header=any(cell.column_header and cell.start_row == row_index for cell in table.cells),
        original_row_sha256=_digest([cell.text for _, cell in _row_source_cells(table, row_index)]),
        # Parser explicitly marks source-table completeness as unverified. Missing coverage
        # is retained as a gap; the chunker never invents a blank cell to fill it.
        completeness_status="unverified",
    )


def _column_label(cell: TableCellStructure) -> str:
    start = cell.start_column + 1
    end = cell.end_column
    return f"열 {start}" if end == start else f"열 {start}-{end}"


def _table_row_text(table: TableStructure, row: TableRowChunkMetadata) -> str:
    lines: list[str] = []
    header_reference_indexes = row.header_cell_indexes
    if row.is_header:
        header_reference_indexes = tuple(
            use.cell_index
            for use in row.cells
            if use.relation == "merged_reference" and use.cell_index in row.header_cell_indexes
        )
    if header_reference_indexes:
        lines.append("[표 헤더 참조]")
        for cell_index in header_reference_indexes:
            cell = table.cells[cell_index]
            lines.append(f"[{_column_label(cell)}] {cell.text}")

    lines.append(f"[원본 표 행 {row.row_index + 1} / 인덱스 {row.row_index}]")
    for use in row.cells:
        if use.relation == "merged_reference" and use.cell_index in row.header_cell_indexes:
            continue
        cell = table.cells[use.cell_index]
        if use.relation == "source":
            lines.append(f"[{_column_label(cell)}] {cell.text}")
        else:
            # 검색 텍스트에는 참조임을 표시하되, 원본 행 셀에는 텍스트를 복제하지 않는다.
            lines.append(
                f"[{_column_label(cell)} 병합 참조: 원본 행 {cell.start_row + 1}] {cell.text}"
            )
    return "\n".join(lines)


def _table_content_hash(
    table: TableStructure,
    row: TableRowChunkMetadata,
    text: str,
) -> str:
    source_cells = _row_source_cells(table, row.row_index)
    return _digest(
        {
            "source_cells": [
                {"cell_index": cell_index, "text": cell.text} for cell_index, cell in source_cells
            ],
            "search_text": text,
        }
    )


def _table_structure_payload(
    table_element: DocumentElement,
    row: TableRowChunkMetadata,
) -> dict[str, object]:
    table = table_element.table
    if table is None:
        raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
    relevant_indexes = tuple(
        dict.fromkeys((*[use.cell_index for use in row.cells], *row.header_cell_indexes))
    )
    return {
        "table_element": {
            "kind": table_element.kind,
            "self_ref": table_element.self_ref,
            "original_text": table_element.original_text,
            "location": asdict(table_element.location),
        },
        "table_dimensions": (table.row_count, table.column_count),
        "row": asdict(row),
        "relevant_cells": [
            {"cell_index": cell_index, "cell": asdict(table.cells[cell_index])}
            for cell_index in relevant_indexes
        ],
    }


def _chunk_id(
    *,
    source_id: str,
    version: str,
    kind: ChunkKind,
    element_ids: tuple[str, ...],
    content_sha256: str,
    structure: object,
) -> str:
    payload = {
        "source_id": source_id,
        "version": version,
        "kind": kind,
        "element_ids": element_ids,
        "content_sha256": content_sha256,
        "structure": structure,
    }
    return f"sha256:{_digest(payload)}"


def _make_document_chunk(
    refs: Sequence[_ElementRef],
    *,
    source_id: str,
    version: str,
    count_tokens: Callable[[str], int],
    target_tokens: int,
    model_status: ModelStatus,
    model_attempts: int,
    model_failure: str | None,
    fallback_used: bool,
) -> DocumentChunk:
    elements = tuple(ref.element for ref in refs)
    element_ids = tuple(ref.element_id for ref in refs)
    text = _join_element_text(refs)
    content_sha256 = _document_content_hash(elements, text)
    table_structure = [asdict(element) for element in elements]
    chunk_id = _chunk_id(
        source_id=source_id,
        version=version,
        kind="document",
        element_ids=element_ids,
        content_sha256=content_sha256,
        structure=table_structure,
    )
    token_count = _validate_token_count(count_tokens, text)
    return DocumentChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        version=version,
        kind="document",
        element_ids=element_ids,
        text=text,
        source_elements=elements,
        table_id=None,
        table_row=None,
        token_count=token_count,
        over_target=token_count > target_tokens,
        content_sha256=content_sha256,
        generation_method="deterministic"
        if fallback_used or model_status == "not_used"
        else "agentic",
        model_status=model_status,
        model_attempts=model_attempts,
        model_failure=model_failure,
        fallback_used=fallback_used,
    )


def _make_table_row_chunk(
    table_element: DocumentElement,
    table_id: str,
    row_index: int,
    *,
    source_id: str,
    version: str,
    count_tokens: Callable[[str], int],
    target_tokens: int,
) -> DocumentChunk:
    table = table_element.table
    if table is None:
        raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
    row = _table_row_metadata(table_element, table_id, row_index)
    text = _table_row_text(table, row)
    content_sha256 = _table_content_hash(table, row, text)
    element_ids = (row.row_id,)
    chunk_id = _chunk_id(
        source_id=source_id,
        version=version,
        kind="table_row",
        element_ids=element_ids,
        content_sha256=content_sha256,
        structure=_table_structure_payload(table_element, row),
    )
    token_count = _validate_token_count(count_tokens, text)
    return DocumentChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        version=version,
        kind="table_row",
        element_ids=element_ids,
        text=text,
        source_elements=(table_element,),
        table_id=table_id,
        table_row=row,
        token_count=token_count,
        over_target=token_count > target_tokens,
        content_sha256=content_sha256,
        generation_method="deterministic",
        model_status="not_used",
        model_attempts=0,
        model_failure=None,
        fallback_used=False,
    )


def _message_content(response: object) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                raise ChunkGroupingResponseError("모델 응답 content가 텍스트가 아닙니다.")
        return "".join(parts)
    raise ChunkGroupingResponseError("모델 응답에 JSON 텍스트가 없습니다.")


def _parse_groups(response: object) -> tuple[tuple[str, ...], ...]:
    try:
        payload = json.loads(_message_content(response))
    except (json.JSONDecodeError, TypeError) as error:
        raise ChunkGroupingResponseError("모델 응답이 유효한 JSON이 아닙니다.") from error
    if not isinstance(payload, dict) or set(payload) != {"groups"}:
        raise ChunkGroupingResponseError("모델 응답은 groups 필드 하나만 포함해야 합니다.")
    raw_groups = payload["groups"]
    if not isinstance(raw_groups, list):
        raise ChunkGroupingResponseError("groups는 비어 있지 않은 ID 목록이어야 합니다.")

    groups: list[tuple[str, ...]] = []
    for group in raw_groups:
        if not isinstance(group, list) or not group:
            raise ChunkGroupingResponseError("groups는 비어 있지 않은 ID 목록이어야 합니다.")
        element_ids: list[str] = []
        for element_id in group:
            if not isinstance(element_id, str):
                raise ChunkGroupingResponseError("groups는 비어 있지 않은 ID 목록이어야 합니다.")
            element_ids.append(element_id)
        groups.append(tuple(element_ids))
    return tuple(groups)


def _validate_groups(
    groups: tuple[tuple[str, ...], ...],
    segments: tuple[tuple[_ElementRef, ...], ...],
    *,
    count_tokens: Callable[[str], int],
    target_tokens: int,
) -> tuple[tuple[_ElementRef, ...], ...]:
    refs = tuple(ref for segment in segments for ref in segment)
    expected_ids = tuple(ref.element_id for ref in refs)
    flattened = tuple(element_id for group in groups for element_id in group)
    if flattened != expected_ids:
        raise ChunkGroupingResponseError(
            "모든 요소 ID를 원문 순서대로 정확히 한 번 포함해야 합니다."
        )
    id_to_ref = {ref.element_id: ref for ref in refs}
    validated: list[tuple[_ElementRef, ...]] = []
    for group in groups:
        group_refs = tuple(id_to_ref[element_id] for element_id in group)
        if len({ref.segment_index for ref in group_refs}) != 1:
            raise ChunkGroupingResponseError("표를 사이에 둔 요소는 한 그룹으로 묶을 수 없습니다.")
        positions = tuple(ref.position for ref in group_refs)
        if positions != tuple(range(positions[0], positions[0] + len(positions))):
            raise ChunkGroupingResponseError("그룹은 원문에서 인접한 요소만 포함해야 합니다.")
        token_count = _validate_token_count(count_tokens, _join_element_text(group_refs))
        if len(group_refs) > 1 and token_count > target_tokens:
            raise ChunkGroupingResponseError("여러 요소 그룹이 목표 토큰 수를 초과했습니다.")
        validated.append(group_refs)
    return tuple(validated)


def _deterministic_groups(
    segments: tuple[tuple[_ElementRef, ...], ...],
    *,
    count_tokens: Callable[[str], int],
    target_tokens: int,
) -> tuple[tuple[_ElementRef, ...], ...]:
    groups: list[tuple[_ElementRef, ...]] = []
    for segment in segments:
        current: list[_ElementRef] = []
        for ref in segment:
            candidate = (*current, ref)
            candidate_tokens = _validate_token_count(
                count_tokens,
                _join_element_text(candidate),
            )
            if current and candidate_tokens > target_tokens:
                groups.append(tuple(current))
                current = [ref]
            else:
                current.append(ref)
        if current:
            groups.append(tuple(current))
    return tuple(groups)


def _prompt_messages(
    segments: tuple[tuple[_ElementRef, ...], ...],
    retry_note: str | None,
    *,
    count_tokens: Callable[[str], int],
    target_tokens: int,
) -> tuple[SystemMessage, HumanMessage]:
    segment_payload = [
        {
            "segment_id": f"s{segment_index + 1:06d}",
            "elements": [
                {
                    "id": ref.element_id,
                    "kind": ref.element.kind,
                    "text": ref.text,
                    "token_count": _validate_token_count(count_tokens, ref.text),
                }
                for ref in segment
            ],
        }
        for segment_index, segment in enumerate(segments)
    ]
    instructions = (
        f"목표는 그룹당 최대 {target_tokens} 토큰입니다. 각 요소의 token_count는 주입된 토큰 계산기 결과입니다. "
        "인접한 일반 문서 요소를 검색 단위 그룹으로 묶으세요. 원문 텍스트를 고치거나 요약하지 마세요. "
        "각 segment 내부에서만 인접한 ID를 묶고, 표 경계를 넘지 말며 모든 ID를 입력 순서대로 정확히 한 번 포함하세요. "
        "단일 요소가 목표를 초과하면 해당 요소를 독립 그룹으로 유지하고 나누지 마세요. "
        "그룹의 실제 검색 텍스트는 요소 사이에 줄바꿈을 넣어 만들며, 그룹 전체 토큰 수는 검증 단계에서 다시 계산됩니다. "
        'JSON만 반환하세요: {"groups":[["e000001","e000002"],["e000003"]]}.'
    )
    if retry_note:
        instructions += f" 이전 응답은 검증에 실패했습니다: {retry_note} 새 JSON을 반환하세요."
    return (
        SystemMessage(content=instructions),
        HumanMessage(
            content=_canonical_json({"target_tokens": target_tokens, "segments": segment_payload})
        ),
    )


def _http_status_code(error: BaseException) -> int | None:
    pending: list[object] = [error]
    visited: set[int] = set()
    first_code: int | None = None
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        for attribute in ("status_code", "status"):
            code = getattr(current, attribute, None)
            if isinstance(code, int):
                if code == 429:
                    return 429
                if first_code is None:
                    first_code = code
        response = getattr(current, "response", None)
        if response is not None:
            pending.append(response)
        for attribute in ("__cause__", "__context__"):
            related = getattr(current, attribute, None)
            if related is not None:
                pending.append(related)
    return first_code


def _model_failure(error: BaseException) -> str:
    status_code = _http_status_code(error)
    prefix = f"HTTP {status_code}: " if status_code is not None else ""
    detail = str(error).strip() or type(error).__name__
    return (prefix + detail)[:500]


async def _agentic_groups(
    model: BaseChatModel,
    segments: tuple[tuple[_ElementRef, ...], ...],
    *,
    count_tokens: Callable[[str], int],
    target_tokens: int,
) -> tuple[tuple[tuple[_ElementRef, ...], ...], int, str | None]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        try:
            response = await model.ainvoke(
                _prompt_messages(
                    segments,
                    _model_failure(last_error) if last_error is not None else None,
                    count_tokens=count_tokens,
                    target_tokens=target_tokens,
                )
            )
            groups = _parse_groups(response)
            validated = _validate_groups(
                groups,
                segments,
                count_tokens=count_tokens,
                target_tokens=target_tokens,
            )
            return validated, attempt, None
        except InvalidTokenCountError:
            raise
        except Exception as error:  # noqa: BLE001 - injected model providers raise different exception types
            last_error = error
            if _http_status_code(error) == 429:
                return (
                    _deterministic_groups(
                        segments,
                        count_tokens=count_tokens,
                        target_tokens=target_tokens,
                    ),
                    attempt,
                    _model_failure(error),
                )

    if last_error is None:
        raise ChunkingError("모델 재시도가 오류 없이 종료됐습니다.")
    return (
        _deterministic_groups(
            segments,
            count_tokens=count_tokens,
            target_tokens=target_tokens,
        ),
        MAX_MODEL_ATTEMPTS,
        _model_failure(last_error),
    )


def _chunk_order_key(chunk: DocumentChunk, element_positions: dict[str, int]) -> tuple[int, int]:
    if chunk.kind == "table_row":
        if chunk.table_id is None or chunk.table_row is None:
            raise ChunkIntegrityError("표 행 청크에 표 메타데이터가 없습니다.")
        table_position = element_positions.get(chunk.table_id)
        if table_position is None:
            raise ChunkIntegrityError("표 행 청크의 상위 표 ID가 없습니다.")
        return table_position, chunk.table_row.row_index
    if not chunk.element_ids:
        raise ChunkIntegrityError("일반 문서 청크에 요소 ID가 없습니다.")
    position = element_positions.get(chunk.element_ids[0])
    if position is None:
        raise ChunkIntegrityError("일반 문서 청크에 알 수 없는 요소 ID가 있습니다.")
    return position, -1


def validate_chunk_integrity(
    structure: DocumentStructure,
    chunks: tuple[DocumentChunk, ...],
    *,
    source_id: str,
    version: str,
    count_tokens: Callable[[str], int],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
) -> None:
    # 출력의 원문 범위, 행 수, 순서, 토큰 수와 결정적 해시를 다시 확인한다.
    segments = _validate_structure(structure)
    id_map = _all_element_ids(structure)
    element_positions = {element_id: position for element_id, (position, _) in id_map.items()}
    expected_document_ids = tuple(ref.element_id for segment in segments for ref in segment)
    observed_document_ids: list[str] = []
    expected_rows: list[tuple[str, int, str]] = []
    observed_rows: list[tuple[str, int, str]] = []
    seen_chunk_ids: set[str] = set()

    for position, element in enumerate(structure.elements):
        if element.kind == "table":
            table_id = _element_id(position)
            if element.table is None:
                raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
            expected_rows.extend(
                (table_id, row_index, _row_id(table_id, row_index))
                for row_index in range(element.table.row_count)
            )

    for chunk in chunks:
        if chunk.source_id != source_id or chunk.version != version:
            raise ChunkIntegrityError("청크의 source_id 또는 version이 입력과 다릅니다.")
        if chunk.chunk_id in seen_chunk_ids:
            raise ChunkIntegrityError("중복 Chunk ID가 있습니다.")
        seen_chunk_ids.add(chunk.chunk_id)
        if chunk.kind == "document":
            if chunk.table_row is not None or chunk.table_id is not None:
                raise ChunkIntegrityError("일반 문서 청크에 표 행 메타데이터가 포함됐습니다.")
            refs: list[_ElementRef] = []
            for element_id in chunk.element_ids:
                source = id_map.get(element_id)
                if source is None or source[1].kind == "table":
                    raise ChunkIntegrityError("일반 문서 청크의 요소 ID가 원문과 다릅니다.")
                element = source[1]
                if not isinstance(element.text, str):
                    raise ChunkIntegrityError("일반 문서 요소에 원문 텍스트가 없습니다.")
                refs.append(
                    _ElementRef(
                        element_id=element_id,
                        position=source[0],
                        element=element,
                        text=element.text,
                        segment_index=-1,
                    )
                )
            if not refs:
                raise ChunkIntegrityError("빈 일반 문서 청크가 있습니다.")
            positions = tuple(ref.position for ref in refs)
            if positions != tuple(range(positions[0], positions[0] + len(positions))):
                raise ChunkIntegrityError("일반 문서 청크가 비인접 요소를 묶었습니다.")
            if any(structure.elements[position].kind == "table" for position in positions):
                raise ChunkIntegrityError("일반 문서 청크가 표를 가로질렀습니다.")
            elements = tuple(ref.element for ref in refs)
            expected_text = _join_element_text(refs)
            expected_hash = _document_content_hash(elements, expected_text)
            expected_id = _chunk_id(
                source_id=source_id,
                version=version,
                kind="document",
                element_ids=chunk.element_ids,
                content_sha256=expected_hash,
                structure=[asdict(element) for element in elements],
            )
            if chunk.source_elements != elements or chunk.text != expected_text:
                raise ChunkIntegrityError("일반 문서 원문 텍스트 또는 구조가 변조됐습니다.")
            observed_document_ids.extend(chunk.element_ids)
            _validate_model_metadata(chunk)
        elif chunk.kind == "table_row":
            if chunk.table_id is None or chunk.table_row is None:
                raise ChunkIntegrityError("표 행 청크에 행 메타데이터가 없습니다.")
            table_source = id_map.get(chunk.table_id)
            if table_source is None or table_source[1].kind != "table":
                raise ChunkIntegrityError("표 행 청크가 원본 표를 참조하지 않습니다.")
            table_element = table_source[1]
            table = table_element.table
            if table is None:
                raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
            row_index = chunk.table_row.row_index
            if not 0 <= row_index < table.row_count:
                raise ChunkIntegrityError("표 행 인덱스가 범위를 벗어났습니다.")
            expected_row = _table_row_metadata(table_element, chunk.table_id, row_index)
            expected_text = _table_row_text(table, expected_row)
            expected_hash = _table_content_hash(table, expected_row, expected_text)
            expected_ids = (expected_row.row_id,)
            expected_id = _chunk_id(
                source_id=source_id,
                version=version,
                kind="table_row",
                element_ids=expected_ids,
                content_sha256=expected_hash,
                structure=_table_structure_payload(table_element, expected_row),
            )
            if (
                chunk.element_ids != expected_ids
                or chunk.table_row != expected_row
                or chunk.source_elements != (table_element,)
                or chunk.text != expected_text
            ):
                raise ChunkIntegrityError("표 행 청크의 원문·셀 참조·병합 구조가 다릅니다.")
            observed_rows.append((chunk.table_id, row_index, expected_row.row_id))
            _validate_model_metadata(chunk)
        else:
            raise ChunkIntegrityError(f"알 수 없는 청크 유형입니다: {chunk.kind}")

        expected_tokens = _validate_token_count(count_tokens, chunk.text)
        if (
            chunk.kind == "document"
            and len(chunk.element_ids) > 1
            and expected_tokens > target_tokens
        ):
            raise ChunkIntegrityError("여러 일반 요소를 묶은 청크가 목표 토큰 수를 초과했습니다.")
        if (
            chunk.content_sha256 != expected_hash
            or chunk.chunk_id != expected_id
            or chunk.token_count != expected_tokens
            or chunk.over_target != (expected_tokens > target_tokens)
        ):
            raise ChunkIntegrityError("청크 해시, 토큰 수 또는 Chunk ID가 원문과 다릅니다.")

    if tuple(observed_document_ids) != expected_document_ids:
        raise ChunkIntegrityError("일반 문서 요소가 누락·중복되었거나 순서가 바뀌었습니다.")
    if observed_rows != expected_rows:
        raise ChunkIntegrityError("원본 표 행이 누락·중복되었거나 순서가 바뀌었습니다.")
    order_keys = tuple(_chunk_order_key(chunk, element_positions) for chunk in chunks)
    if order_keys != tuple(sorted(order_keys)):
        raise ChunkIntegrityError("최종 청크 순서가 원문 순서와 다릅니다.")


def _validate_model_metadata(chunk: DocumentChunk) -> None:
    if not isinstance(chunk.fallback_used, bool):
        raise ChunkIntegrityError("fallback_used는 불리언이어야 합니다.")

    if (
        isinstance(chunk.model_attempts, bool)
        or not isinstance(chunk.model_attempts, int)
        or not 0 <= chunk.model_attempts <= MAX_MODEL_ATTEMPTS
    ):
        raise ChunkIntegrityError("모델 시도 횟수가 허용 범위를 벗어났습니다.")

    if chunk.kind == "table_row":
        if (
            chunk.generation_method != "deterministic"
            or chunk.model_status != "not_used"
            or chunk.model_attempts != 0
            or chunk.model_failure is not None
            or chunk.fallback_used is not False
        ):
            raise ChunkIntegrityError("표 행 청크는 LLM 미사용 결정적 생성 메타데이터여야 합니다.")
        return

    if chunk.kind != "document":
        raise ChunkIntegrityError(f"알 수 없는 청크 유형입니다: {chunk.kind}")

    if chunk.model_status == "succeeded":
        if (
            chunk.generation_method != "agentic"
            or not 1 <= chunk.model_attempts <= MAX_MODEL_ATTEMPTS
            or chunk.model_failure is not None
            or chunk.fallback_used is not False
        ):
            raise ChunkIntegrityError("Agentic 성공 메타데이터 조합이 유효하지 않습니다.")
        return

    if chunk.model_status == "failed":
        if (
            chunk.generation_method != "deterministic"
            or not 1 <= chunk.model_attempts <= MAX_MODEL_ATTEMPTS
            or chunk.model_failure is None
            or chunk.fallback_used is not True
        ):
            raise ChunkIntegrityError("결정적 fallback 메타데이터 조합이 유효하지 않습니다.")
        return

    raise ChunkIntegrityError("일반 문서 청크는 Agentic 성공 또는 fallback 실패 상태여야 합니다.")


async def chunk_document(
    structure: DocumentStructure,
    *,
    source_id: str,
    version: str,
    model: BaseChatModel,
    count_tokens: Callable[[str], int],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
) -> tuple[DocumentChunk, ...]:
    # 일반 요소는 인접 그룹으로, 표는 원본 행마다 하나의 청크로 만든다.
    # 병합 셀의 원문은 소유 행에 두고 후속 행의 검색 텍스트에는 참조로 표시한다.
    if not source_id or not version:
        raise ChunkingError("source_id와 version은 외부에서 제공해야 합니다.")
    if isinstance(target_tokens, bool) or not isinstance(target_tokens, int) or target_tokens <= 0:
        raise ChunkingError("target_tokens는 양의 정수여야 합니다.")
    if not isinstance(model, BaseChatModel):
        raise TypeError("model은 외부에서 주입한 BaseChatModel이어야 합니다.")

    segments = _validate_structure(structure)
    chunks: list[DocumentChunk] = []
    all_general_refs = tuple(ref for segment in segments for ref in segment)
    if all_general_refs:
        groups, attempts, failure = await _agentic_groups(
            model,
            segments,
            count_tokens=count_tokens,
            target_tokens=target_tokens,
        )
        model_status: ModelStatus = "failed" if failure is not None else "succeeded"
        fallback_used = failure is not None
        for group in groups:
            chunks.append(
                _make_document_chunk(
                    group,
                    source_id=source_id,
                    version=version,
                    count_tokens=count_tokens,
                    target_tokens=target_tokens,
                    model_status=model_status,
                    model_attempts=attempts,
                    model_failure=failure,
                    fallback_used=fallback_used,
                )
            )

    for position, element in enumerate(structure.elements):
        if element.kind != "table":
            continue
        table = element.table
        if table is None:
            raise ChunkIntegrityError("표 요소에 TableStructure가 없습니다.")
        table_id = _element_id(position)
        for row_index in range(table.row_count):
            chunks.append(
                _make_table_row_chunk(
                    element,
                    table_id,
                    row_index,
                    source_id=source_id,
                    version=version,
                    count_tokens=count_tokens,
                    target_tokens=target_tokens,
                )
            )

    element_positions = {
        element_id: position for element_id, (position, _) in _all_element_ids(structure).items()
    }
    chunks.sort(key=lambda chunk: _chunk_order_key(chunk, element_positions))
    result = tuple(chunks)
    validate_chunk_integrity(
        structure,
        result,
        source_id=source_id,
        version=version,
        count_tokens=count_tokens,
        target_tokens=target_tokens,
    )
    return result
