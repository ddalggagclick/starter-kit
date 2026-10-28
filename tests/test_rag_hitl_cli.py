"""CLI HITL guard tests. No real PDF parsing, Ollama, embedding or DB calls."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from rag_test_fixtures import hitl_document
from starter_rag import cli as rag_cli
from starter_rag.ingestion.cli import assist_review
from starter_rag.ingestion.parser import (
    DocumentConversionError,
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    TableStructure,
)
from starter_rag.ingestion.review import (
    apply_corrections,
    approve_review,
    create_review,
    read_review,
    write_review,
)


class RagHitlCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.pdf = Path(self.tempdir.name) / "input.pdf"
        self.pdf.write_bytes(b"fake-pdf-for-test")
        self.review = Path(self.tempdir.name) / "review.json"

    def _export(self):
        with (
            patch.object(rag_cli, "parse_document", return_value=object()),
            patch.object(rag_cli, "extract_document_structure", return_value=hitl_document()),
            redirect_stdout(StringIO()) as output,
        ):
            status = rag_cli.main(
                [
                    "review",
                    "export",
                    str(self.pdf),
                    "--output",
                    str(self.review),
                    "--source-id",
                    "guide-1",
                    "--version",
                    "v1",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["issue_count"], 1)

    def _valid_draft(self) -> dict:
        self._export()
        data = json.loads(self.review.read_text(encoding="utf-8"))
        correction = data["corrections"][0]
        correction["action"] = "replace"
        removed = correction["replacement_cells"].pop()
        correction["detached_notes"].append(removed["text"])
        self.review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def test_검토_내보내기와_미완료_검증을_수행한다(self):
        self._export()
        with redirect_stderr(StringIO()):
            self.assertEqual(rag_cli.main(["review", "validate", str(self.review)]), 2)

    def test_유효한_Draft_검증은_기존_계약을_유지한다(self):
        self._valid_draft()
        with redirect_stdout(StringIO()) as output:
            status = rag_cli.main(["review", "validate", str(self.review)])

        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["approval"], "draft")
        self.assertEqual(set(result), {"success", "issue_count", "corrected_elements", "approval"})
        self.assertNotIn("review_sha256", result)

    def test_승인된_검토_검증은_승인_콘텐츠_해시를_표시한다(self):
        self._valid_draft()
        approved = approve_review(self.review)
        with redirect_stdout(StringIO()) as output:
            status = rag_cli.main(["review", "validate", str(self.review)])

        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["approval"], "approved")
        self.assertEqual(result["review_sha256"], approved["approval"]["content_sha256"])

    def test_승인_후_수정한_검토는_해시_검증에_실패한다(self):
        self._valid_draft()
        approve_review(self.review)
        data = json.loads(self.review.read_text(encoding="utf-8"))
        data["corrections"][0]["detached_notes"][0] += " changed"
        self.review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with redirect_stderr(StringIO()):
            status = rag_cli.main(["review", "validate", str(self.review)])

        self.assertEqual(status, 2)

    def test_승인_상태만_바꾼_검토는_해시_검증에_실패한다(self):
        data = self._valid_draft()
        data["approval"]["state"] = "approved"
        self.review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with redirect_stderr(StringIO()):
            status = rag_cli.main(["review", "validate", str(self.review)])

        self.assertEqual(status, 2)

    def test_scan의_Docling_변환_오류는_안전한_종료코드로_반환한다(self):
        absolute_path = "/Users/private/original.pdf"
        stderr = StringIO()
        with (
            patch.object(
                rag_cli,
                "parse_document",
                side_effect=DocumentConversionError(f"Docling failed at {absolute_path}"),
            ),
            redirect_stdout(StringIO()) as stdout,
            redirect_stderr(stderr),
        ):
            status = rag_cli.main(["review", "scan", str(self.pdf)])

        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("PDF 파싱 오류", stderr.getvalue())
        self.assertNotIn(absolute_path, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_export의_Docling_변환_오류는_검토파일을_만들지_않는다(self):
        absolute_path = "/Users/private/original.pdf"
        stderr = StringIO()
        with (
            patch.object(
                rag_cli,
                "parse_document",
                side_effect=DocumentConversionError(f"Docling failed at {absolute_path}"),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(stderr),
        ):
            status = rag_cli.main(["review", "export", str(self.pdf), "--output", str(self.review)])

        self.assertEqual(status, 2)
        self.assertFalse(self.review.exists())
        self.assertIn("PDF 파싱 오류", stderr.getvalue())
        self.assertNotIn(absolute_path, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_wizard의_Docling_변환_오류는_승인_색인_게시를_진행하지_않는다(self):
        absolute_path = "/Users/private/original.pdf"
        review_path = Path(self.tempdir.name) / "wizard-review.json"
        stderr = StringIO()
        with (
            patch.object(
                rag_cli,
                "parse_document",
                side_effect=DocumentConversionError(f"Docling failed at {absolute_path}"),
            ),
            patch.object(rag_cli, "assist_review") as assist,
            patch.object(rag_cli, "_index_file") as index,
            patch.object(rag_cli, "_publish") as publish,
            redirect_stdout(StringIO()),
            redirect_stderr(stderr),
        ):
            status = rag_cli.main(
                [
                    "review",
                    "wizard",
                    str(self.pdf),
                    "--output",
                    str(review_path),
                    "--index",
                    "--publish",
                ]
            )

        self.assertEqual(status, 2)
        self.assertFalse(review_path.exists())
        self.assertIn("PDF 파싱 오류", stderr.getvalue())
        self.assertNotIn(absolute_path, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        assist.assert_not_called()
        index.assert_not_called()
        publish.assert_not_called()

    def test_유효한_수정이_없으면_승인을_거부한다(self):
        self._export()
        with redirect_stderr(StringIO()):
            self.assertEqual(rag_cli.main(["review", "approve", str(self.review)]), 2)

    def test_기존_검토없는_게시_경로를_유지한다(self):
        with patch.object(rag_cli, "_publish", return_value=0) as publish:
            status = rag_cli.main(["publish", "--source-id", "guide-1", "--version", "v1"])
        self.assertEqual(status, 0)
        publish.assert_called_once_with("guide-1", "v1", "published-guides")

    def test_검토가_원본_식별자와_일치해야_한다(self):
        self._export()
        data = json.loads(self.review.read_text(encoding="utf-8"))
        corr = data["corrections"][0]
        corr["action"] = "replace"
        corr["detached_notes"] = [corr["replacement_cells"].pop()["text"]]
        self.review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        approve_review(self.review)
        with redirect_stderr(StringIO()):
            data, structure = rag_cli.read_review(
                self.review, require_approved=True, source_id="guide-1", version="v1"
            )
            self.assertEqual(len(structure.elements), 4)
            self.assertEqual(data["approval"]["state"], "approved")
            with self.assertRaises(ValueError):
                rag_cli.read_review(self.review, require_approved=True, version="v2")

    def test_승인된_검토_구조를_사용해_원본을_다시_파싱하지_않는다(self):
        structure = hitl_document()
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(rag_cli, "read_review", return_value=({}, structure)) as read_review,
            patch.object(rag_cli, "parse_document") as parse_document,
            patch.object(
                rag_cli,
                "_load_tokenizer",
                return_value=SimpleNamespace(encode=lambda text, **_: text.split()),
            ),
            patch.object(
                rag_cli, "chunk_document_with_config", new_callable=AsyncMock, return_value=()
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            status = rag_cli.main(
                [
                    "chunk",
                    str(self.pdf),
                    "--tokenizer-path",
                    "local-tokenizer",
                    "--review-file",
                    str(self.review),
                ]
            )

        self.assertEqual(status, 0, stderr.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())["success"])
        parse_document.assert_not_called()
        read_review.assert_called_once()


class HitlWizardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pdf = Path(temp.name) / "example.pdf"
        self.pdf.write_bytes(b"local-original")
        self.file = Path(temp.name) / "example-review.json"
        write_review(
            self.file, create_review(self.pdf, hitl_document(), source_id="guide-1", version="v1")
        )

    def test_빈_표_복원은_대화형_검토에서_사람확인을_요구한다(self):
        empty_file = self.file.with_name("empty-review.json")
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
        write_review(empty_file, create_review(self.pdf, empty, source_id="guide-1", version="v1"))
        answers = iter(["1", "1", "1", "1", "Recovered value", "0", "1", "0", "1", "y", "n"])

        with redirect_stdout(StringIO()):
            self.assertFalse(assist_review(empty_file, prompt=lambda _: next(answers)))

        report = json.loads(empty_file.read_text(encoding="utf-8"))
        correction = report["corrections"][0]
        self.assertTrue(correction["visual_confirmation"])
        self.assertEqual(correction["replacement_cells"][0]["text"], "Recovered value")
        self.assertEqual(report["approval"]["state"], "draft")
        self.assertEqual(
            apply_corrections(report).elements[0].table.cells[0].text, "Recovered value"
        )

    def test_셀_위치_수정은_대화형_검토에서_저장된다(self):
        answers = iter(["2", "3", "3", "4", "0", "1", "5", "n"])

        with redirect_stdout(StringIO()):
            self.assertFalse(assist_review(self.file, prompt=lambda _: next(answers)))

        correction = json.loads(self.file.read_text(encoding="utf-8"))["corrections"][0]
        moved = correction["replacement_cells"][3]
        self.assertEqual((moved["start_row"], moved["end_row"]), (3, 4))
        self.assertEqual((moved["start_column"], moved["end_column"]), (0, 1))

    def test_대화형_검토가_저장과_승인을_수행한다(self):
        answers = iter(["1", "3", "Separate value", "5", "y"])
        with redirect_stdout(StringIO()):
            self.assertTrue(assist_review(self.file, prompt=lambda _: next(answers)))
        data, result = read_review(self.file, require_approved=True)
        self.assertEqual(data["approval"]["state"], "approved")
        self.assertEqual(result.elements[2].text, "Separate value")

    def test_대화형_검토를_저장한_뒤_재개한다(self):
        answers = iter(["0"])
        with redirect_stdout(StringIO()):
            self.assertFalse(assist_review(self.file, prompt=lambda _: next(answers)))
        self.assertTrue(self.file.exists())
        self.assertEqual(
            json.loads(self.file.read_text(encoding="utf-8"))["approval"]["state"], "draft"
        )

    def test_검토_불러오기가_식별자를_전달하고_게시한다(self):
        answers = iter(["1", "3", "Separate value", "5", "y"])
        with redirect_stdout(StringIO()):
            assist_review(self.file, prompt=lambda _: next(answers))
        with (
            patch.object(rag_cli, "_index_file", return_value=0) as index,
            patch.object(rag_cli, "_publish", return_value=0) as publish,
            redirect_stdout(StringIO()),
        ):
            status = rag_cli.main(
                [
                    "review",
                    "load",
                    str(self.file),
                    "--publisher",
                    "General publisher",
                    "--tokenizer-path",
                    "/fake/tokenizer",
                    "--publish",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(index.call_args.kwargs["source_id"], "guide-1")
        self.assertEqual(index.call_args.kwargs["version"], "v1")
        self.assertEqual(index.call_args.kwargs["review_file"], str(self.file))
        publish.assert_called_once()

    def test_색인에_실패하면_검토_불러오기가_게시하지_않는다(self):
        answers = iter(["1", "3", "Separate value", "5", "y"])
        with redirect_stdout(StringIO()):
            assist_review(self.file, prompt=lambda _: next(answers))
        with (
            patch.object(rag_cli, "_index_file", return_value=1),
            patch.object(rag_cli, "_publish") as publish,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            status = rag_cli.main(
                [
                    "review",
                    "load",
                    str(self.file),
                    "--publisher",
                    "General publisher",
                    "--tokenizer-path",
                    "/fake/tokenizer",
                    "--publish",
                ]
            )
        self.assertEqual(status, 1)
        publish.assert_not_called()

    def test_검토_마법사는_원본을_한_번만_파싱하고_덮어쓰지_않는다(self):
        with (
            patch.object(rag_cli, "parse_document", return_value=object()) as parser,
            patch.object(rag_cli, "extract_document_structure", return_value=hitl_document()),
            patch("builtins.input", side_effect=["1", "3", "Separate value", "5", "y"]),
            redirect_stdout(StringIO()),
        ):
            status = rag_cli.main(
                [
                    "review",
                    "wizard",
                    str(self.pdf),
                    "--output",
                    str(self.file) + "-new",
                    "--source-id",
                    "guide-1",
                    "--version",
                    "v1",
                ]
            )
        self.assertEqual(status, 0)
        parser.assert_called_once()
        self.assertTrue(Path(str(self.file) + "-new").exists())

    def test_검토_마법사는_출력_경로를_명시해야_한다(self):
        stderr = StringIO()
        with (
            patch.object(rag_cli, "parse_document") as parser,
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as error,
        ):
            rag_cli.main(["review", "wizard", str(self.pdf)])

        self.assertEqual(error.exception.code, 2)
        self.assertIn("--output", stderr.getvalue())
        parser.assert_not_called()
        self.assertFalse(self.pdf.parent.joinpath("results", "example-review.json").exists())


if __name__ == "__main__":
    unittest.main()
