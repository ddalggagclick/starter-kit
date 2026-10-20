# 담당: [D] | 책임: Docling 기반 공식 안내자료 문서 변환.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-1
# 구현할 기능: 로컬 PDF/DOCX/HTML을 DoclingDocument로 변환하고 실패 유형을 구분한다.
# 완료 기준: Docling 성공 상태의 변환 결과를 반환하고, 입력·변환 실패를 각각 식별한다.
# 제한사항: 명시적으로 호출한 파일만 변환하며 법령 원문을 벡터 색인하지 않는다.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from docling_core.types.doc.document import DoclingDocument

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".html", ".htm"})
LocationStatus = Literal["verified", "not_applicable", "unverified"]


@dataclass(frozen=True)
class DocumentBoundingBox:
    """Docling에서 제공한 원문 좌표."""

    left: float
    top: float
    right: float
    bottom: float
    coordinate_origin: str


@dataclass(frozen=True)
class SourceProvenance:
    """Docling 요소의 페이지·좌표·문자 범위 정보."""

    page_no: int | None
    bbox: DocumentBoundingBox | None
    charspan: tuple[int, int] | None


@dataclass(frozen=True)
class DocumentLocation:
    status: LocationStatus
    page_numbers: tuple[int, ...]
    provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True)
class TableCellStructure:
    text: str
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
class TableRowStructure:
    row_index: int
    cell_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TableStructure:
    row_count: int
    column_count: int
    rows: tuple[TableRowStructure, ...]
    cells: tuple[TableCellStructure, ...]


@dataclass(frozen=True)
class DocumentElement:
    kind: Literal["document_title", "section_title", "paragraph", "table"]
    text: str | None
    original_text: str | None
    self_ref: str | None
    level: int | None
    location: DocumentLocation
    table: TableStructure | None


@dataclass(frozen=True)
class UnverifiedItem:
    self_ref: str | None
    kind: Literal["location", "table_completeness"]
    reason: str


@dataclass(frozen=True)
class DocumentStructure:
    source_format: str | None
    elements: tuple[DocumentElement, ...]
    unverified_items: tuple[UnverifiedItem, ...]


class UnsupportedDocumentFormatError(ValueError):
    """입력 확장자가 Docling 변환 어댑터에서 지원되지 않는다."""


class DocumentReadError(OSError):
    """입력 파일을 확인하거나 읽을 수 없다."""


class DocumentConversionError(RuntimeError):
    """Docling 변환이 실패했거나 성공 문서를 반환하지 않았다."""


def _source_format(document: DoclingDocument, source_path: str | Path | None) -> str | None:
    if source_path is not None:
        suffix = Path(source_path).suffix.lower().lstrip(".")
        if suffix:
            return "html" if suffix in {"html", "htm"} else suffix

    origin = getattr(document, "origin", None)
    filename = getattr(origin, "filename", None)
    suffix = Path(filename).suffix.lower().lstrip(".") if filename else ""
    mimetype = str(getattr(origin, "mimetype", "")).lower()
    if suffix in {"html", "htm"} or mimetype in {"text/html", "application/xhtml+xml"}:
        return "html"
    if suffix in {"pdf", "docx"}:
        return suffix
    if mimetype == "application/pdf":
        return "pdf"
    if "wordprocessingml.document" in mimetype:
        return "docx"
    return suffix or None


def _bounding_box(value: object) -> DocumentBoundingBox | None:
    if value is None:
        return None
    try:
        coordinates = (
            float(getattr(value, "l")),
            float(getattr(value, "t")),
            float(getattr(value, "r")),
            float(getattr(value, "b")),
        )
    except (AttributeError, TypeError, ValueError):
        return None

    origin = getattr(value, "coord_origin", "")
    return DocumentBoundingBox(
        left=coordinates[0],
        top=coordinates[1],
        right=coordinates[2],
        bottom=coordinates[3],
        coordinate_origin=str(getattr(origin, "value", origin)),
    )


def _provenance(item: object) -> tuple[SourceProvenance, ...]:
    result: list[SourceProvenance] = []
    for item_provenance in getattr(item, "prov", ()) or ():
        page_no = getattr(item_provenance, "page_no", None)
        if not isinstance(page_no, int):
            page_no = None
        raw_charspan = getattr(item_provenance, "charspan", None)
        charspan = None
        if (
            isinstance(raw_charspan, (tuple, list))
            and len(raw_charspan) == 2
            and all(isinstance(value, int) for value in raw_charspan)
        ):
            charspan = (raw_charspan[0], raw_charspan[1])
        result.append(
            SourceProvenance(
                page_no=page_no,
                bbox=_bounding_box(getattr(item_provenance, "bbox", None)),
                charspan=charspan,
            )
        )
    return tuple(result)


def _location(
    item: object,
    source_format: str | None,
) -> DocumentLocation:
    provenance = _provenance(item)
    if source_format == "html":
        status: LocationStatus = "not_applicable"
        page_numbers: tuple[int, ...] = ()
    else:
        has_position = any(
            item_provenance.page_no is not None and item_provenance.bbox is not None
            for item_provenance in provenance
        )
        status = "verified" if has_position else "unverified"
        page_numbers = tuple(
            dict.fromkeys(
                item_provenance.page_no
                for item_provenance in provenance
                if item_provenance.page_no is not None
            )
        )
    return DocumentLocation(
        status=status,
        page_numbers=page_numbers,
        provenance=provenance,
    )


def _table_structure(item: object) -> TableStructure:
    data = getattr(item, "data", None)
    raw_cells = getattr(data, "table_cells", ()) or ()
    cells: list[TableCellStructure] = []
    for cell in raw_cells:
        cell_ref = getattr(cell, "ref", None)
        self_ref = getattr(cell_ref, "cref", None) or getattr(cell_ref, "self_ref", None)
        cells.append(
            TableCellStructure(
                text=str(getattr(cell, "text", "")),
                start_row=int(getattr(cell, "start_row_offset_idx", 0)),
                end_row=int(getattr(cell, "end_row_offset_idx", 0)),
                start_column=int(getattr(cell, "start_col_offset_idx", 0)),
                end_column=int(getattr(cell, "end_col_offset_idx", 0)),
                row_span=int(getattr(cell, "row_span", 1)),
                column_span=int(getattr(cell, "col_span", 1)),
                column_header=bool(getattr(cell, "column_header", False)),
                row_header=bool(getattr(cell, "row_header", False)),
                row_section=bool(getattr(cell, "row_section", False)),
                fillable=bool(getattr(cell, "fillable", False)),
                self_ref=self_ref,
                bbox=_bounding_box(getattr(cell, "bbox", None)),
            )
        )

    row_count = int(getattr(data, "num_rows", 0) or 0)
    column_count = int(getattr(data, "num_cols", 0) or 0)
    rows = tuple(
        TableRowStructure(
            row_index=row_index,
            cell_indexes=tuple(
                cell_index
                for cell_index, cell in enumerate(cells)
                if cell.start_row == row_index
            ),
        )
        for row_index in range(max(row_count, 0))
    )
    return TableStructure(
        row_count=row_count,
        column_count=column_count,
        rows=rows,
        cells=tuple(cells),
    )


def extract_document_structure(
    document: DoclingDocument,
    source_path: str | Path | None = None,
) -> DocumentStructure:
    """Docling 요소를 원문 순서로 구조화하고 확인되지 않은 위치를 표시한다."""
    source_format = _source_format(document, source_path)
    elements: list[DocumentElement] = []
    unverified_items: list[UnverifiedItem] = []

    for item, _level in document.iterate_items():
        label = getattr(getattr(item, "label", None), "value", getattr(item, "label", None))
        self_ref = getattr(item, "self_ref", None)
        table = None
        if label == "title":
            kind: Literal["document_title", "section_title", "paragraph", "table"] = "document_title"
        elif label == "section_header":
            kind = "section_title"
        elif label in {"paragraph", "text"}:
            kind = "paragraph"
        elif label == "table":
            kind = "table"
            table = _table_structure(item)
        else:
            continue

        location = _location(item, source_format)
        text = None if table is not None else getattr(item, "text", "")
        elements.append(
            DocumentElement(
                kind=kind,
                text=text,
                original_text=getattr(item, "orig", None),
                self_ref=self_ref,
                level=getattr(item, "level", None) if kind == "section_title" else None,
                location=location,
                table=table,
            )
        )
        if location.status == "unverified":
            unverified_items.append(
                UnverifiedItem(
                    self_ref=self_ref,
                    kind="location",
                    reason="Docling 결과에 검증 가능한 페이지 번호와 좌표 provenance가 없습니다.",
                )
            )
        if table is not None:
            unverified_items.append(
                UnverifiedItem(
                    self_ref=self_ref,
                    kind="table_completeness",
                    reason="Docling 변환 결과만으로 원본 표의 누락 여부를 확인할 수 없습니다.",
                )
            )

    return DocumentStructure(
        source_format=source_format,
        elements=tuple(elements),
        unverified_items=tuple(unverified_items),
    )


def _create_converter() -> DocumentConverter:
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.HTML]
    )


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    return _create_converter()


def _validate_source(source: Path) -> None:
    try:
        source.stat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"문서 파일이 없습니다: {source}") from error
    except OSError as error:
        raise DocumentReadError(f"문서 파일을 확인할 수 없습니다: {source}") from error

    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentFormatError(
            f"지원하지 않는 문서 형식입니다: {source.suffix or '(확장자 없음)'}"
        )

    try:
        with source.open("rb") as document_file:
            document_file.read(1)
    except OSError as error:
        raise DocumentReadError(f"문서 파일을 읽을 수 없습니다: {source}") from error


def parse_document(path: str | Path) -> DoclingDocument:
    source = Path(path)
    _validate_source(source)

    try:
        result = _get_converter().convert(source, raises_on_error=False)
    except Exception as error:
        raise DocumentConversionError(
            f"Docling 변환에 실패했습니다: {source}"
        ) from error

    status = getattr(result.status, "value", result.status)
    # 일부 페이지나 구조만 변환된 결과도 정상 문서로 넘기지 않는다.
    if status != "success":
        raise DocumentConversionError(
            f"Docling 변환 상태가 성공이 아닙니다: {source} ({status})"
        )

    document = getattr(result, "document", None)
    if document is None:
        raise DocumentConversionError(f"Docling 결과에 문서가 없습니다: {source}")
    return document
