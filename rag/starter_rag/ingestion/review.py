# 담당: [D] | 책임: PDF 표 구조의 사람 검토와 승인 기록을 검증한다.
# 구현할 기능: 원본 스냅샷·수정 문자 보존·승인 해시를 확인한다.
# 완료 기준: 원문 변조와 미완료 검토를 거부하며, 승인자를 인증하는 수단으로 오인하지 않는다.
# 제한사항: 검토 파일 해시는 비밀키 서명이나 권한 확인이 아니다.

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from getpass import getuser
from hashlib import sha256
from pathlib import Path
from typing import Any

from starter_rag.ingestion.chunking import ChunkIntegrityError, _validate_structure
from starter_rag.ingestion.parser import (
    DocumentBoundingBox,
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    SourceProvenance,
    TableCellStructure,
    TableRowStructure,
    TableStructure,
    UnverifiedItem,
)

SCHEMA_VERSION = 1


class ReviewError(ValueError):
    """Review, correction or approval did not satisfy the contract."""


def _digest(data: Any) -> str:
    return sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _bbox(data: dict | None) -> DocumentBoundingBox | None:
    return DocumentBoundingBox(**data) if data else None


def _location(data: dict) -> DocumentLocation:
    return DocumentLocation(
        status=data["status"],
        page_numbers=tuple(data["page_numbers"]),
        provenance=tuple(
            SourceProvenance(
                page_no=item["page_no"],
                bbox=_bbox(item["bbox"]),
                charspan=tuple(item["charspan"]) if item["charspan"] is not None else None,
            )
            for item in data["provenance"]
        ),
    )


def _cell(data: dict) -> TableCellStructure:
    names = (
        "text",
        "start_row",
        "end_row",
        "start_column",
        "end_column",
        "row_span",
        "column_span",
        "column_header",
        "row_header",
        "row_section",
        "fillable",
        "self_ref",
    )
    return TableCellStructure(**{key: data[key] for key in names}, bbox=_bbox(data.get("bbox")))


def _table(data: dict | None) -> TableStructure | None:
    if data is None:
        return None
    cells = tuple(_cell(item) for item in data["cells"])
    row_count = data["row_count"]
    column_count = data["column_count"]
    if (
        type(row_count) is not int
        or type(column_count) is not int
        or not 0 <= row_count <= 10000
        or not 0 <= column_count <= 10000
    ):
        raise ReviewError("표의 행·열 수가 올바르지 않습니다.")
    if (row_count == 0 or column_count == 0) and (row_count, column_count, cells) != (0, 0, ()):
        raise ReviewError("빈 표는 0×0 크기이며 셀이 없어야 합니다.")
    return TableStructure(
        row_count=row_count,
        column_count=column_count,
        cells=cells,
        rows=tuple(
            TableRowStructure(i, tuple(j for j, c in enumerate(cells) if c.start_row == i))
            for i in range(row_count)
        ),
    )


def _structure(data: dict) -> DocumentStructure:
    elements = tuple(
        DocumentElement(
            kind=item["kind"],
            text=item["text"],
            original_text=item["original_text"],
            self_ref=item["self_ref"],
            level=item["level"],
            location=_location(item["location"]),
            table=_table(item["table"]),
        )
        for item in data["elements"]
    )
    unverified = tuple(UnverifiedItem(**item) for item in data["unverified_items"])
    return DocumentStructure(data["source_format"], elements, unverified)


def detect_table_issues(structure: DocumentStructure) -> list[dict]:
    issues: list[dict] = []
    for position, element in enumerate(structure.elements):
        if element.kind != "table":
            continue
        table_id = f"e{position + 1:06d}"
        table = element.table
        if table is None:
            issues.append(
                {
                    "table_id": table_id,
                    "problem": "missing_table",
                    "page_numbers": list(element.location.page_numbers),
                }
            )
            continue
        occupied: dict[tuple[int, int], int] = {}
        collisions: list[dict] = []
        invalid: list[int] = []
        for i, cell in enumerate(table.cells):
            if not (
                0 <= cell.start_row < cell.end_row <= table.row_count
                and 0 <= cell.start_column < cell.end_column <= table.column_count
                and cell.row_span == cell.end_row - cell.start_row
                and cell.column_span == cell.end_column - cell.start_column
            ):
                invalid.append(i)
                continue
            for row in range(cell.start_row, cell.end_row):
                for col in range(cell.start_column, cell.end_column):
                    previous = occupied.setdefault((row, col), i)
                    if previous != i:
                        collisions.append({"row": row, "column": col, "cells": [previous, i]})
        geometry_invalid = table.row_count < 1 or table.column_count < 1 or invalid or collisions
        single_cell_fragment = (
            table.row_count == 1
            and table.column_count == 1
            and len(table.cells) == 1
            and len(_normalized(table.cells[0].text)) == 1
        )
        if geometry_invalid or single_cell_fragment:
            issues.append(
                {
                    "table_id": table_id,
                    "problem": (
                        "invalid_table_geometry"
                        if geometry_invalid
                        else "single_cell_text_fragment"
                    ),
                    "page_numbers": list(element.location.page_numbers),
                    "invalid_cells": invalid,
                    "collisions": collisions,
                    "cells": [asdict(c) for c in table.cells],
                }
            )
    return issues


def create_review(
    source: Path, structure: DocumentStructure, *, source_id: str, version: str
) -> dict:
    if not source_id.strip() or not version.strip():
        raise ReviewError("source_id와 version이 필요합니다.")
    source = source.resolve()
    original = asdict(structure)
    issues = detect_table_issues(structure)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(source),
            "sha256": _source_digest(source),
            "source_id": source_id,
            "version": version,
        },
        "original": original,
        "original_sha256": _digest(original),
        "issues": issues,
        "corrections": [
            {
                "table_id": issue["table_id"],
                "action": "pending",
                "replacement_cells": deepcopy(issue.get("cells", [])),
                "row_count": structure.elements[int(issue["table_id"][1:]) - 1].table.row_count
                if structure.elements[int(issue["table_id"][1:]) - 1].table
                else None,
                "column_count": structure.elements[
                    int(issue["table_id"][1:]) - 1
                ].table.column_count
                if structure.elements[int(issue["table_id"][1:]) - 1].table
                else None,
                "detached_notes": [],
                "acknowledged_cell_indexes": [],
                "source_page_numbers": issue["page_numbers"],
                "visual_confirmation": False,
            }
            for issue in issues
        ],
        "approval": {"state": "draft", "content_sha256": None},
    }


def _approval_content(data: dict) -> dict:
    return {key: value for key, value in data.items() if key != "approval"}


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def apply_corrections(data: dict, *, require_approved: bool = False) -> DocumentStructure:
    """Validate source snapshot, preserve original text, rebuild corrected tables.

    No Docling execution or LLM calls take place here.
    """
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ReviewError("지원하지 않는 검토 JSON 버전입니다.")
    source_info = data.get("source") or {}
    source_path = Path(source_info.get("path", ""))
    if not source_path.is_file() or _source_digest(source_path) != source_info.get("sha256"):
        raise ReviewError("원본 PDF가 없거나 원본 해시가 변경됐습니다.")
    original = data.get("original")
    if not isinstance(original, dict) or _digest(original) != data.get("original_sha256"):
        raise ReviewError("원본 파싱 스냅샷이 변경됐습니다.")
    structure = _structure(original)
    issues = detect_table_issues(structure)
    if issues != data.get("issues"):
        raise ReviewError("검토 대상 목록이 원본 구조와 다릅니다.")
    corrections = data.get("corrections")
    if not isinstance(corrections, list):
        raise ReviewError("corrections는 목록이어야 합니다.")
    correction_ids = [item.get("table_id") for item in corrections]
    issue_ids = [item["table_id"] for item in issues]
    if len(set(correction_ids)) != len(correction_ids) or set(correction_ids) != set(issue_ids):
        raise ReviewError("수정 항목은 검출된 문제 표와 정확히 대응해야 합니다.")
    if require_approved:
        approval = data.get("approval") or {}
        if (
            approval.get("state") != "approved"
            or approval.get("content_sha256") != _digest(_approval_content(data))
            or not isinstance(approval.get("approved_by"), str)
            or not approval["approved_by"].strip()
            or not isinstance(approval.get("approved_at"), str)
            or not approval["approved_at"].strip()
        ):
            raise ReviewError("승인 기록이 없거나 승인 후 검토 내용이 변경됐습니다.")
    items = []
    correction_map = {entry["table_id"]: entry for entry in corrections}
    for position, element in enumerate(structure.elements):
        table_id = f"e{position + 1:06d}"
        if table_id not in correction_map:
            items.append(element)
            continue
        correction = correction_map[table_id]
        action = correction.get("action")
        if action not in {"replace", "recover_from_pdf"}:
            raise ReviewError(f"{table_id}: 수정 방법을 확정해야 합니다.")
        original_table = element.table
        if original_table is None:
            raise ReviewError(f"{table_id}: 원본 표 데이터가 없습니다.")
        raw_cells = correction.get("replacement_cells")
        notes = correction.get("detached_notes")
        acknowledged = correction.get("acknowledged_cell_indexes")
        if (
            not isinstance(raw_cells, list)
            or not isinstance(notes, list)
            or not isinstance(acknowledged, list)
        ):
            raise ReviewError(
                f"{table_id}: replacement_cells, detached_notes, acknowledged_cell_indexes는 목록이어야 합니다."
            )
        if not all(isinstance(note, str) and note.strip() for note in notes):
            raise ReviewError(f"{table_id}: 분리 문구는 비어 있을 수 없습니다.")
        if len(set(acknowledged)) != len(acknowledged) or any(
            type(i) is not int or not 0 <= i < len(original_table.cells) for i in acknowledged
        ):
            raise ReviewError(f"{table_id}: 변경 승인 셀 번호가 잘못됐습니다.")
        try:
            cells = tuple(_cell(raw) for raw in raw_cells)
        except (KeyError, TypeError, ValueError) as exc:
            raise ReviewError(f"{table_id}: 셀 필드가 유효하지 않습니다.") from exc
        recovering = action == "recover_from_pdf"
        if any(
            not isinstance(c.text, str) or (not c.text.strip() and not recovering) for c in cells
        ):
            raise ReviewError(
                f"{table_id}: 빈 셀은 원문 확인을 기록한 PDF 표 복원에서만 허용됩니다."
            )
        recoverable_empty_table = (
            not original_table.cells
            and original_table.row_count == 0
            and original_table.column_count == 0
            and not acknowledged
        )
        recoverable_single_cell_fragment = (
            original_table.row_count == 1
            and original_table.column_count == 1
            and len(original_table.cells) == 1
            and len(_normalized(original_table.cells[0].text)) == 1
            and set(acknowledged) == set(range(len(original_table.cells)))
        )
        if recovering and (
            not (recoverable_empty_table or recoverable_single_cell_fragment)
            or not cells
            or correction.get("visual_confirmation") is not True
            or correction.get("source_page_numbers") != list(element.location.page_numbers)
        ):
            raise ReviewError(
                f"{table_id}: 복원 가능한 원문 표의 PDF 페이지 대조와 셀 확인이 필요합니다."
            )
        # Acknowledgment must not authorize silent deletion or invention.
        # Even split/reordered table cells must preserve the complete character
        # inventory. Whitespace may change when reconstructing table footnotes.
        original_characters = Counter(
            "".join(_normalized(cell.text) for cell in original_table.cells)
        )
        revised_characters = Counter(
            "".join(_normalized(cell.text) for cell in cells)
            + "".join(_normalized(note) for note in notes)
        )
        if not recovering and original_characters != revised_characters:
            missing = sum((original_characters - revised_characters).values())
            added = sum((revised_characters - original_characters).values())
            raise ReviewError(
                f"{table_id}: 원문 문자 보존 실패 (누락 {missing}, 추가 {added}). "
                "셀·분리 문구를 원본과 다시 대조하세요."
            )
        output_texts = [_normalized(c.text) for c in cells] + [_normalized(note) for note in notes]
        # A changed original cell requires explicit human acknowledgment; no silent text removal.
        for i, old_cell in enumerate(original_table.cells):
            if (
                _normalized(old_cell.text)
                and not any(_normalized(old_cell.text) in value for value in output_texts)
                and i not in acknowledged
            ):
                raise ReviewError(
                    f"{table_id}: 원본 셀 {i} 텍스트 누락 또는 수정. acknowledged_cell_indexes 확인 필요"
                )
        updated = _table(
            {
                "row_count": correction.get("row_count"),
                "column_count": correction.get("column_count"),
                "cells": [asdict(c) for c in cells],
            }
        )
        items.append(replace(element, table=updated))
        for note_index, note in enumerate(notes, 1):
            items.append(
                DocumentElement(
                    kind="paragraph",
                    text=note,
                    original_text=note,
                    self_ref=f"{element.self_ref or table_id}:hitl-note:{note_index}",
                    level=None,
                    location=element.location,
                    table=None,
                )
            )
    result = replace(structure, elements=tuple(items))
    try:
        _validate_structure(result)
    except ChunkIntegrityError as exc:
        raise ReviewError(f"보정 후 청킹 구조 검증 실패: {exc}") from exc
    return result


def read_review(
    path: Path,
    *,
    require_approved: bool = False,
    source: Path | None = None,
    source_id: str | None = None,
    version: str | None = None,
) -> tuple[dict, DocumentStructure]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewError("검토 JSON을 읽을 수 없습니다.") from exc
    info = data.get("source") or {}
    if source is not None and Path(info.get("path", "")).resolve() != source.resolve():
        raise ReviewError("검토 파일의 원본 경로가 입력 문서와 다릅니다.")
    if source_id is not None and info.get("source_id") != source_id:
        raise ReviewError("검토 파일의 source_id가 다릅니다.")
    if version is not None and info.get("version") != version:
        raise ReviewError("검토 파일의 version이 다릅니다.")
    return data, apply_corrections(data, require_approved=require_approved)


def approve_review(path: Path) -> dict:
    data, _ = read_review(path)
    data["approval"] = {
        "state": "approved",
        "content_sha256": _digest(_approval_content(data)),
        "approved_by": getuser(),
        "approved_at": datetime.now(UTC).isoformat(),
    }
    # Atomic replacement: never leave a truncated approval record behind.
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            temporary.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
    return data


def write_review(path: Path, data: dict) -> None:
    if path.exists():
        raise ReviewError("검토 파일이 이미 존재합니다. 기존 결과를 덮어쓰지 않습니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            temporary.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
