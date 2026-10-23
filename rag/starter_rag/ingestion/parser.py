# 담당: [D] | 책임: Docling 문서 변환과 Source_v2 XLSX 검증.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-1
# 구현할 기능: Docling 입력 형식을 변환하고 Source_v2 승인·URL·행 정보를 검증한다.
# 완료 기준: 문서 변환 결과와 Source_v2 검증 결과를 기존 파서 경계에서 반환한다.
# 제한사항: 명시적으로 호출한 파일만 변환하며 법령 원문을 벡터 색인하지 않는다.

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from docling_core.types.doc.document import DoclingDocument

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

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

    return DocumentConverter(allowed_formats=list(InputFormat))


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

    from docling.datamodel.base_models import FormatToExtensions

    source_name = source.name.lower()
    supported_suffixes = (
        f".{extension.lower().lstrip('.')}"
        for extensions in FormatToExtensions.values()
        for extension in extensions
    )
    if not any(source_name.endswith(suffix) for suffix in supported_suffixes):
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


SHEET = "RAG_Unit본문"
APPROVED = "적재 승인"
EXPECTED_NO_URL = frozenset(
    {
        "U-06-BANK-KB",
        "U-06-BANK-NH",
        "U-06-BANK-WOORI",
        "U-06-BANK-HANA",
        "U-08-SKT",
        "U-08-KT",
        "U-08-LGU",
    }
)
HEADERS = (
    "Unit ID",
    "Unit 목록 행",
    "절차·주제",
    "연결된 기본 카드",
    "공식 URL (내부 출처)",
    "화면 URL 사용",
    "연결한 링크 행",
    "RAG 인용 발췌 본문 (링크 H열 원문)",
    "투입 조건 (Unit F)",
    "미확인·유의 (Unit G)",
    "공식 원문 위치 메모 (Unit J)",
    "버전·기준일 (Unit K)",
    "적재 승인",
    "본문 범위",
    "사용 주의",
    "기관·발행처",
    "원본 링크 위치",
    "소스 변경키",
)
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


class SourceV2Error(ValueError):
    """정리된 입력이 불완전하거나 서로 일치하지 않을 때 발생한다."""


@dataclass(frozen=True)
class SourceUnit:
    source_id: str
    row: int
    original_unit_row: int
    title: str
    card: str
    official_url: str | None
    display_link_allowed: bool
    excerpt_rows: tuple[int, ...]
    excerpt: str
    condition: str
    unverified: str
    official_location_note: str
    version_note: str
    approval: str
    scope: str
    caution: str
    publisher: str
    historical_positions: tuple[str, ...]
    content_key: str


def _column(cell_ref: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[1-9][0-9]*", cell_ref)
    if not match:
        raise SourceV2Error("invalid XLSX cell address")
    index = 0
    for letter in match.group(1):
        index = 26 * index + ord(letter) - ord("A") + 1
    return index - 1


def _text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{NS}}}t"))


def _sheet_rows(path: Path) -> list[tuple[int, dict[int, str]]]:
    if path.stat().st_size > 30_000_000:
        raise SourceV2Error("workbook exceeds 30 MB")
    try:
        return _read_xlsx_rows(path)
    except SourceV2Error:
        raise
    except (BadZipFile, KeyError, ET.ParseError, ValueError) as error:
        raise SourceV2Error("invalid XLSX workbook structure") from error


def _read_xlsx_rows(path: Path) -> list[tuple[int, dict[int, str]]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relations}
        sheets = list(workbook.iter(f"{{{NS}}}sheet"))
        if len(sheets) != 1 or sheets[0].get("name") != SHEET:
            raise SourceV2Error("Source_v2 must contain only RAG_Unit본문")
        target = targets[sheets[0].attrib[f"{{{REL}}}id"]]
        sheet_file = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        if not sheet_file.startswith("xl/") or ".." in sheet_file.split("/"):
            raise SourceV2Error("unsafe worksheet location")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [_text(node) for node in strings.iter(f"{{{NS}}}si")]
        root = ET.fromstring(archive.read(sheet_file))
        rows: list[tuple[int, dict[int, str]]] = []
        for row in root.iter(f"{{{NS}}}row"):
            cells: dict[int, str] = {}
            for cell in row.findall(f"{{{NS}}}c"):
                kind = cell.get("t")
                value = cell.find(f"{{{NS}}}v")
                if kind == "inlineStr":
                    inline = cell.find(f"{{{NS}}}is")
                    raw = _text(inline) if inline is not None else ""
                elif kind == "s" and value is not None:
                    raw = shared[int(value.text or "0")]
                else:
                    raw = value.text if value is not None and value.text else ""
                cells[_column(cell.attrib["r"])] = raw
            rows.append((int(row.attrib["r"]), cells))
        return rows


def _url(value: str) -> str | None:
    if not value:
        return None
    if value.strip() != value or any(char.isspace() or ord(char) < 32 for char in value):
        raise SourceV2Error("invalid HTTPS URL")
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
        )
        _ = parts.port
    except ValueError as exc:
        raise SourceV2Error("invalid HTTPS URL") from exc
    if not valid:
        raise SourceV2Error("invalid HTTPS URL")
    return value


def _positive_integer(value: str, label: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise SourceV2Error(f"invalid {label}")
    return int(value)


def read_source_units(path: str | Path, *, enforce_baseline: bool = True) -> tuple[SourceUnit, ...]:
    """31개 유닛이 들어 있는 단일 시트 통합문서의 자체 일관성을 검증한다.

    보존된 과거 행 참조는 출처 표기이며 현재 셀 주소가 아니다.
    이 참조만으로 발췌문이 삭제된 시트의 원문과 일치한다고 증명할 수 없다.
    """
    rows = _sheet_rows(Path(path))
    if not rows or rows[0][0] != 1:
        raise SourceV2Error("empty or missing header row")
    headers = {value.strip(): index for index, value in rows[0][1].items() if value.strip()}
    if len(headers) != sum(bool(x.strip()) for x in rows[0][1].values()):
        raise SourceV2Error("duplicate column heading")
    missing = set(HEADERS) - headers.keys()
    if missing:
        raise SourceV2Error(f"missing columns: {sorted(missing)}")
    seen: set[str] = set()
    results: list[SourceUnit] = []
    for row_number, cells in rows[1:]:

        def field(key: str, row_cells: dict[int, str] = cells) -> str:
            return row_cells.get(headers[key], "")

        sid = field("Unit ID").strip()
        if not sid:
            if any(x.strip() for x in cells.values()):
                raise SourceV2Error(f"missing Unit ID at row {row_number}")
            continue
        if not re.fullmatch(r"U-[A-Z0-9-]+", sid) or sid in seen:
            raise SourceV2Error(f"duplicate or invalid Unit ID: {sid}")
        seen.add(sid)
        if field("적재 승인").strip() != APPROVED:
            raise SourceV2Error(f"not approved: {sid}")
        title = field("절차·주제").strip()
        publisher = field("기관·발행처").strip()
        excerpt = field("RAG 인용 발췌 본문 (링크 H열 원문)")
        if not title or not publisher or not excerpt.strip():
            raise SourceV2Error(f"missing required title, publisher, or excerpt: {sid}")
        url = _url(field("공식 URL (내부 출처)").strip())
        display = field("화면 URL 사용").strip()
        if display not in ("표시", "표시 금지 / 없음"):
            raise SourceV2Error(f"invalid display rule: {sid}")
        if display == "표시" and url is None:
            raise SourceV2Error(f"cannot display nonexistent URL: {sid}")
        row_list = [part.strip() for part in field("연결한 링크 행").split(",")]
        positions = [part.strip() for part in field("원본 링크 위치").split(";")]
        numbers = tuple(_positive_integer(x, "historical link row") for x in row_list)
        expected_positions = tuple(f"SU_링크기록(전체)!H{n}" for n in numbers)
        if (
            not numbers
            or len(numbers) != len(set(numbers))
            or tuple(positions) != expected_positions
        ):
            raise SourceV2Error(f"historical excerpt positions disagree: {sid}")
        condition = field("투입 조건 (Unit F)")
        unverified = field("미확인·유의 (Unit G)")
        expected_key = hashlib.sha256(
            (sid + "\n" + excerpt + "\n" + condition + "\n" + unverified).encode("utf-8")
        ).hexdigest()
        if field("소스 변경키").strip() != expected_key:
            raise SourceV2Error(f"content key mismatch: {sid}")
        results.append(
            SourceUnit(
                source_id=sid,
                row=row_number,
                original_unit_row=_positive_integer(field("Unit 목록 행").strip(), "Unit row"),
                title=title,
                card=field("연결된 기본 카드"),
                official_url=url,
                display_link_allowed=display == "표시",
                excerpt_rows=numbers,
                excerpt=excerpt,
                condition=condition,
                unverified=unverified,
                official_location_note=field("공식 원문 위치 메모 (Unit J)"),
                version_note=field("버전·기준일 (Unit K)"),
                approval=APPROVED,
                scope=field("본문 범위"),
                caution=field("사용 주의"),
                publisher=publisher,
                historical_positions=expected_positions,
                content_key=expected_key,
            )
        )
    if enforce_baseline:
        if len(results) != 31:
            raise SourceV2Error(f"expected 31 approved Units, received {len(results)}")
        no_url = {unit.source_id for unit in results if unit.official_url is None}
        if no_url != EXPECTED_NO_URL:
            raise SourceV2Error(f"unexpected URL-free Units: {sorted(no_url)}")
    return tuple(results)


def inspect_source_v2(path: str | Path) -> dict[str, object]:
    units = read_source_units(path)
    return {
        "source_v2_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "sheet": SHEET,
        "approved": len(units),
        "without_url": sum(unit.official_url is None for unit in units),
        "with_url": sum(unit.official_url is not None for unit in units),
        "display_allowed": sum(unit.display_link_allowed for unit in units),
        "mapping_pairs": sum(len(unit.excerpt_rows) for unit in units),
        "source_units": [asdict(unit) for unit in units],
        "historical_rows_are_live_links": False,
        "official_source_freshness_verified": False,
    }
