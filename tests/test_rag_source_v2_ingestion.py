"""DB 쓰기나 모델·Docling 다운로드 없이 Source_v2 행 매핑을 검증한다."""

from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starter_rag.ingestion.parser import SourceV2Error, inspect_source_v2, read_source_units
from starter_rag.ingestion.service import (
    _content_hash,
    _version,
    assign_source_rows,
    verify_source_rows,
)


@dataclass(frozen=True)
class FakeLocation:
    status: str = "unverified"
    page_numbers: tuple[int, ...] = ()
    provenance: tuple[()] = ()


def fake_row(unit, **overrides):
    row = SimpleNamespace(
        chunk_id=f"sheet:row:{unit.row}",
        source_id="source-v2-worksheet",
        version="source-v2-table",
        kind="table_row",
        table_row=SimpleNamespace(row_index=unit.row - 1),
        generation_method="deterministic",
        model_status="not_used",
        model_attempts=0,
        fallback_used=False,
        content_sha256="0" * 64,
        text=f"[열 1] {unit.source_id} [열 8] {unit.excerpt}",
        element_ids=("e000001",),
        locations=(FakeLocation(),),
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


@unittest.skipUnless(os.getenv("SOURCE_V2_FILE"), "SOURCE_V2_FILE required")
class OneSheetSourceV2IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(os.environ["SOURCE_V2_FILE"])
        self.units = read_source_units(self.path)

    def test_승인유닛과과거발췌위치개수를확인한다(self):
        report = inspect_source_v2(self.path)
        self.assertEqual(report["sheet"], "RAG_Unit본문")
        self.assertEqual(report["approved"], 31)
        self.assertEqual(report["mapping_pairs"], 41)
        self.assertEqual(report["without_url"], 7)
        self.assertEqual(report["display_allowed"], 16)
        self.assertFalse(report["historical_rows_are_live_links"])

    def test_각유닛에실제표행하나만연결한다(self):
        chunks = tuple(fake_row(unit) for unit in self.units)
        selected = assign_source_rows(self.units, chunks)
        self.assertEqual(len(selected), 31)
        self.assertEqual(len({x.chunk_id for x in selected.values()}), 31)
        for unit in self.units:
            result = selected[unit.source_id]
            self.assertEqual(result.kind, "table_row")
            self.assertEqual(result.source_id, unit.source_id)
            self.assertEqual(result.version, _version(unit))
            self.assertIn(unit.excerpt, result.text)
            self.assertIn("source_v2_row", result.location)
            self.assertIn('"chunk_kind": "table_row"', result.location)
            # 비공개 공식 URL은 사용자에게 반환할 Evidence 본문에 넣지 않는다.
            if unit.official_url:
                self.assertNotIn(unit.official_url, result.text)

    def test_불일치하거나비결정적인행을거부한다(self):
        chunks = tuple(fake_row(unit) for unit in self.units)
        with self.assertRaises(SourceV2Error):
            assign_source_rows(self.units, chunks[:-1])
        with self.assertRaises(SourceV2Error):
            assign_source_rows(
                self.units, (fake_row(self.units[0], model_status="succeeded"),) + chunks[1:]
            )
        with self.assertRaises(SourceV2Error):
            assign_source_rows(self.units, (fake_row(self.units[0], text="wrong ID"),) + chunks[1:])

    def test_데이터베이스없이기존행청킹으로파싱흐름을검증한다(self):
        class FakeTokenizer:
            def encode(self, value, add_special_tokens=False):
                return list(value)

        tokenizer = FakeTokenizer()

        async def chunk_document_with_config(structure, **kwargs):
            self.assertEqual(kwargs["source_id"], "source-v2-worksheet")
            return tuple(fake_row(u) for u in self.units)

        with (
            patch("starter_rag.ingestion.service.parse_document", return_value="parsed-xlsx"),
            patch(
                "starter_rag.ingestion.service.extract_document_structure",
                return_value=SimpleNamespace(
                    source_format="xlsx",
                    elements=[SimpleNamespace(kind="table")],
                ),
            ),
            patch(
                "starter_rag.ingestion.service.chunk_document_with_config",
                new_callable=AsyncMock,
                side_effect=chunk_document_with_config,
            ),
        ):
            units, rows = asyncio.run(
                verify_source_rows(
                    self.path,
                    count_tokens=lambda value: len(
                        tokenizer.encode(value, add_special_tokens=False)
                    ),
                )
            )
        self.assertEqual(len(units), 31)
        self.assertEqual(len(rows), 31)
        self.assertEqual(rows[self.units[0].source_id].kind, "table_row")

    def test_게시출처정보가바뀌면버전도바뀐다(self):
        from dataclasses import replace

        u = self.units[0]
        self.assertNotEqual(
            _content_hash(u), _content_hash(replace(u, excerpt=u.excerpt + " 변경"))
        )
        self.assertNotEqual(
            _version(u), _version(replace(u, display_link_allowed=not u.display_link_allowed))
        )


if __name__ == "__main__":
    unittest.main()
