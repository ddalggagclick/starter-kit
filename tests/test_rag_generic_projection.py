# 담당: [통합] | 책임: 범용 XLSX 행 프로젝션의 기존 식별자 호환 및 도메인 독립성 검증.
# 구현할 기능: 구성 데이터만 바꿔 서로 다른 원본 형식을 색인할 수 있는지 확인한다.
# 완료 기준: Source_v2 기존 버전·Evidence ID 보존 및 비결정적 행 거부.
"""Pure projection tests; no DB writes or external model calls."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_core")

from starter_rag.ingestion.service import (  # noqa: I001 - import follows optional-dependency skip
    ProjectionError,
    RowProjectionSpec,
    project_verified_rows,
    projection_from_mapping,
    read_mapped_xlsx,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING = json.loads((ROOT / "rag/examples/source_v2_mapping.json").read_text())


def _chunk(source_id="ID-01", excerpt="text", *, deterministic=True):
    return SimpleNamespace(
        chunk_id="original",
        text=f"{source_id}: {excerpt}",
        kind="table_row",
        table_row=SimpleNamespace(row_index=1),
        content_sha256="0" * 64,
        generation_method="deterministic" if deterministic else "llm",
        model_status="not_used",
        fallback_used=False,
        model_attempts=0,
        element_ids=("element",),
        locations=(),
    )


def test_unrelated_domain_uses_same_generic_projector():
    spec = RowProjectionSpec(
        id_field="id",
        row_field="row",
        excerpt_field="body",
        internal_url_field="url",
        display_url_field="public",
        hash_fields=(("id", "id"), ("body", "body")),
        searchable_fields=(("Body", "body"),),
        location_fields=(("original_row", "row"),),
        location_constants=(("kind", "table_row"),),
        location_row_index_key="row_index",
        location_provenance_key="provenance",
        version_prefix="v-",
    )
    data = {"id": "ID-01", "row": 2, "body": "text", "url": None, "public": False}
    result = project_verified_rows((data,), (_chunk(),), spec)
    assert result["ID-01"].source_id == "ID-01"
    assert result["ID-01"].version.startswith("v-")
    with pytest.raises(ProjectionError):
        project_verified_rows((data,), (_chunk(deterministic=False),), spec)


def test_url_is_not_included_when_link_is_hidden():
    spec = projection_from_mapping(MAPPING)
    fake = {
        "source_id": "ID-01",
        "row": 2,
        "excerpt": "text",
        "title": "title",
        "publisher": "publisher",
        "official_url": "https://example.org/private",
        "display_link_allowed": False,
        "condition": "",
        "unverified": "",
        "scope": "",
        "caution": "",
        "official_location_note": "",
        "version_note": "",
        "historical_positions": (),
    }
    result = project_verified_rows((fake,), (_chunk(),), spec)
    assert "https://example.org/private" not in result["ID-01"].text


def test_source_v2_actual_workbook_optional(monkeypatch):
    import os

    file = os.environ.get("SOURCE_V2_FILE")
    if not file:
        pytest.skip("SOURCE_V2_FILE required for actual workbook validation")
    from starter_rag.ingestion.parser import read_source_units
    from starter_rag.ingestion.service import _content_hash, content_hash

    units = read_source_units(file)
    records = read_mapped_xlsx(file, MAPPING)
    spec = projection_from_mapping(MAPPING)
    assert len(units) == len(records) == 31
    assert all(_content_hash(u) == content_hash(r, spec) for u, r in zip(units, records))
