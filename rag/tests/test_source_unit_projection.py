"""Source Unit 행 본문과 버전 투영을 DB 없이 검증한다."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from starter_rag.ingestion.parser import SourceUnit, read_source_units
from starter_rag.ingestion.service import (
    _content_hash,
    _searchable_row_text,
    _version,
    assign_source_rows,
)

WORKBOOK = Path(__file__).resolve().parents[1] / "data" / "Source_v3.xlsx"


def _row(unit):
    return SimpleNamespace(
        chunk_id=f"row-{unit.row}",
        text=f"{unit.source_id} {unit.excerpt}",
        kind="table_row",
        table_row=SimpleNamespace(row_index=unit.row - 1),
        content_sha256="0" * 64,
        generation_method="deterministic",
        model_status="not_used",
        fallback_used=False,
        model_attempts=0,
        element_ids=("element",),
        locations=(),
    )


def _unit():
    return SourceUnit(
        source_id="U-TEST",
        row=2,
        original_unit_row=2,
        title="제목",
        card="카드",
        official_url="https://example.org/guide",
        display_link_allowed=True,
        excerpt_rows=(2,),
        excerpt="기간 3개월\n필요 서류 안내",
        condition="작성자 지시",
        unverified="미확인 메모",
        official_location_note="원문 위치",
        version_note="기준일",
        approval="승인",
        scope="내부 범위",
        caution="내부 주의",
        publisher="발행처",
        historical_positions=("SU_링크기록(전체)!H2",),
        content_key="key",
    )


def _assert_clean_projection(unit):
    row = assign_source_rows((unit,), (_row(unit),))[unit.source_id]
    expected = (
        f"Source Unit: {unit.source_id}\n절차·주제: {unit.title}\n"
        f"확인한 내용·유의 (인용 발췌): {unit.excerpt}"
    )
    assert row.text == expected
    assert _searchable_row_text(unit) == expected
    assert row.version == _version(unit)
    assert row.version.startswith("source-v2-text-v2-")
    assert "작성자 지시" not in row.text
    assert "미확인 메모" not in row.text
    assert "내부 범위" not in row.text
    assert "내부 주의" not in row.text
    assert row.location
    return row


def test_Source_Unit_색인에는_ID_제목_H열과_새_버전이_포함된다():
    unit = _unit()
    row = _assert_clean_projection(unit)
    assert "기간 3개월\n필요 서류 안내" in row.text
    assert row.version != "source-v2-" + _content_hash(unit)[:16]


@pytest.mark.skipif(not WORKBOOK.exists(), reason="Source_v3.xlsx is not available locally")
def test_Source_v3_31개_Unit의_전체_H열만_색인한다():
    units = read_source_units(WORKBOOK)
    rows = assign_source_rows(units, tuple(_row(unit) for unit in units))
    assert len(rows) == 31
    for unit in units:
        row = rows[unit.source_id]
        assert row.text == (
            f"Source Unit: {unit.source_id}\n절차·주제: {unit.title}\n"
            f"확인한 내용·유의 (인용 발췌): {unit.excerpt}"
        )
        assert row.version == _version(unit)


def test_원본_콘텐츠_해시는_기존_형식을_유지한다():
    unit = _unit()
    data = asdict(unit)
    payload = {
        "source_id": data["source_id"],
        "title": data["title"],
        "publisher": data["publisher"],
        "excerpt": data["excerpt"],
        "condition": data["condition"],
        "unverified": data["unverified"],
        "scope": data["scope"],
        "caution": data["caution"],
        "official_url": data["official_url"],
        "display_link_allowed": data["display_link_allowed"],
        "official_location_note": data["official_location_note"],
        "version_note": data["version_note"],
        "xlsx_row": data["row"],
        "historical_positions": data["historical_positions"],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert _content_hash(unit) == hashlib.sha256(encoded.encode()).hexdigest()
