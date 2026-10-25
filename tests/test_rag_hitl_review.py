"""HITL data preservation and approval tests; no PDF/Ollama/DB required."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from rag_test_fixtures import hitl_cell, hitl_document
from starter_rag.ingestion.parser import (
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    TableRowStructure,
    TableStructure,
)
from starter_rag.ingestion.review import (
    ReviewError,
    apply_corrections,
    approve_review,
    create_review,
    detect_table_issues,
    read_review,
    write_review,
)


class RagHitlReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = Path(self.tmp.name) / "sample.pdf"
        self.pdf.write_bytes(b"test-source-original")
        self.path = Path(self.tmp.name) / "review.json"
        self.structure = hitl_document()

    def _review(self) -> dict:
        return create_review(self.pdf, self.structure, source_id="guide-1", version="v1")

    def _correct(self, data: dict) -> dict:
        correction = data["corrections"][0]
        correction["action"] = "replace"
        removed = correction["replacement_cells"].pop()
        correction["detached_notes"].append(removed["text"])
        return data

    def test_겹친_셀을_탐지하고_두_텍스트를_보존한다(self):
        issues = detect_table_issues(self.structure)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["table_id"], "e000002")
        self.assertEqual(issues[0]["collisions"][0]["cells"], [2, 3])
        self.assertEqual(issues[0]["page_numbers"], [2])

    def test_미완료_검토를_거부한다(self):
        data = self._review()
        with self.assertRaises(ReviewError):
            apply_corrections(data)

    def test_빈_원본_표는_복원_전에_시각_확인이_필요하다(self):
        empty = DocumentStructure(
            "pdf",
            (
                DocumentElement(
                    "table",
                    None,
                    None,
                    "#/tables/1",
                    None,
                    DocumentLocation("verified", (2,), ()),
                    TableStructure(0, 0, (), ()),
                ),
            ),
            (),
        )
        review = create_review(self.pdf, empty, source_id="guide-1", version="v1")
        correction = review["corrections"][0]
        correction.update(
            action="recover_from_pdf",
            row_count=1,
            column_count=1,
            replacement_cells=[asdict(hitl_cell("Recovered value", 0, 1, 0, 1))],
        )
        with self.assertRaisesRegex(ReviewError, "PDF 페이지 대조"):
            apply_corrections(review)
        correction["visual_confirmation"] = True
        result = apply_corrections(review)
        self.assertEqual(result.elements[0].table.cells[0].text, "Recovered value")

    def test_짧은_단일셀_복원은_빈_입력란과_병합을_보존한다(self):
        location = DocumentLocation("verified", (13,), ())
        fragment = DocumentStructure(
            "pdf",
            (
                DocumentElement(
                    "table",
                    None,
                    None,
                    "#/tables/1",
                    None,
                    location,
                    TableStructure(
                        row_count=1,
                        column_count=1,
                        rows=(TableRowStructure(0, (0,)),),
                        cells=(hitl_cell("?", 0, 1, 0, 1),),
                    ),
                ),
            ),
            (),
        )
        review = create_review(self.pdf, fragment, source_id="guide-1", version="v1")
        self.assertEqual(review["issues"][0]["problem"], "single_cell_text_fragment")
        correction = review["corrections"][0]
        cells = [
            hitl_cell("Header", 0, 1, 0, 3),
            hitl_cell("Label", 1, 2, 0, 1),
            hitl_cell("", 1, 2, 1, 3),
            hitl_cell("Second label", 2, 3, 0, 1),
            hitl_cell("", 2, 3, 1, 2),
            hitl_cell("Yes / no", 2, 3, 2, 3),
        ]
        replacement_cells = [asdict(cell) for cell in cells]
        replacement_cells[2]["fillable"] = True
        replacement_cells[4]["fillable"] = True
        correction.update(
            action="recover_from_pdf",
            row_count=3,
            column_count=3,
            replacement_cells=replacement_cells,
            source_page_numbers=[13],
            visual_confirmation=True,
        )
        with self.assertRaisesRegex(ReviewError, "셀 확인"):
            apply_corrections(review)
        correction["acknowledged_cell_indexes"] = [0]

        restored = apply_corrections(review).elements[0].table

        self.assertEqual((restored.row_count, restored.column_count), (3, 3))
        self.assertEqual(
            [cell.text for cell in restored.cells],
            ["Header", "Label", "", "Second label", "", "Yes / no"],
        )
        self.assertEqual([cell.column_span for cell in restored.cells], [3, 1, 2, 1, 1, 1])
        self.assertTrue(restored.cells[2].fillable)
        self.assertTrue(restored.cells[4].fillable)
        self.assertEqual(review["approval"], {"state": "draft", "content_sha256": None})

    def test_분리한_셀의_텍스트와_원본_위치를_보존한다(self):
        data = self._correct(self._review())
        output = apply_corrections(data)
        self.assertEqual(len(output.elements), 4)
        self.assertEqual(output.elements[2].text, "Separate value")
        self.assertEqual(output.elements[2].location.page_numbers, (2,))
        self.assertEqual(len(output.elements[1].table.cells), 3)
        self.assertFalse(detect_table_issues(output))

    def test_승인_검토를_원본과_수정내용에_묶는다(self):
        write_review(self.path, self._correct(self._review()))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        with self.assertRaises(ReviewError):
            read_review(self.path, require_approved=True)
        approve_review(self.path)
        _, result = read_review(
            self.path, require_approved=True, source=self.pdf, source_id="guide-1", version="v1"
        )
        self.assertEqual(len(result.elements), 4)
        data = json.loads(self.path.read_text())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertTrue(data["approval"]["approved_by"])
        self.assertTrue(data["approval"]["approved_at"].endswith("+00:00"))
        data["corrections"][0]["detached_notes"][0] += " edited"
        self.path.write_text(json.dumps(data))
        with self.assertRaises(ReviewError):
            read_review(self.path, require_approved=True)

    def test_원본이_바뀌면_승인을_무효화한다(self):
        write_review(self.path, self._correct(self._review()))
        approve_review(self.path)
        self.pdf.write_bytes(b"changed-pdf-bytes")
        with self.assertRaises(ReviewError):
            read_review(self.path, require_approved=True)

    def test_조용한_텍스트_손실을_막는다(self):
        data = self._review()
        correction = data["corrections"][0]
        correction["action"] = "replace"
        correction["replacement_cells"].pop()
        with self.assertRaisesRegex(ReviewError, "문자 보존 실패"):
            apply_corrections(data)

    def test_확인_표시만으로_원문을_삭제할_수_없다(self):
        data = self._review()
        correction = data["corrections"][0]
        correction["action"] = "replace"
        correction["replacement_cells"] = correction["replacement_cells"][:-1]
        correction["acknowledged_cell_indexes"] = [3]
        with self.assertRaisesRegex(ReviewError, "문자 보존 실패"):
            apply_corrections(data)

    def test_조각을_옮겨도_원문_문자_구성을_보존한다(self):
        data = self._correct(self._review())
        correction = data["corrections"][0]
        correction["detached_notes"] = ["Separate ", "value"]
        correction["acknowledged_cell_indexes"] = [3]
        output = apply_corrections(data)
        self.assertEqual([e.text for e in output.elements[2:4]], ["Separate ", "value"])

    def test_원문에_없는_문자를_거부한다(self):
        data = self._correct(self._review())
        data["corrections"][0]["detached_notes"][0] += "A"
        with self.assertRaisesRegex(ReviewError, "문자 보존 실패"):
            apply_corrections(data)

    def test_수정_후에도_잘못된_표_위치를_거부한다(self):
        data = self._review()
        data["corrections"][0]["action"] = "replace"
        with self.assertRaisesRegex(ReviewError, "검증 실패"):
            apply_corrections(data)

    def test_정상_표에는_수정이_필요하지_않다(self):
        healthy = hitl_document(conflict=False)
        data = create_review(self.pdf, healthy, source_id="guide-1", version="v1")
        self.assertEqual(data["issues"], [])
        self.assertEqual(data["corrections"], [])
        write_review(self.path, data)
        approve_review(self.path)
        _, structure = read_review(self.path, require_approved=True)
        self.assertEqual(len(structure.elements), 3)

    def test_다른_원본이나_버전을_거부한다(self):
        write_review(self.path, self._correct(self._review()))
        approve_review(self.path)
        with self.assertRaises(ReviewError):
            read_review(self.path, require_approved=True, source_id="DIFFERENT")
        with self.assertRaises(ReviewError):
            read_review(self.path, require_approved=True, version="v2")

    def test_검토_내보내기가_기존_파일을_덮어쓰지_않는다(self):
        write_review(self.path, self._review())
        with self.assertRaises(ReviewError):
            write_review(self.path, self._review())


if __name__ == "__main__":
    unittest.main()
