from __future__ import annotations

import builtins
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.items.table.table_data import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel

from starter_rag.ingestion import parser
from starter_rag import cli as rag_cli
from starter_rag.ingestion.parser import (
    DocumentConversionError,
    DocumentReadError,
    UnsupportedDocumentFormatError,
    extract_document_structure,
    parse_document,
)


class DoclingParserAdapterTests(unittest.TestCase):
    def _assert_mocked_format(self, extension: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / f"synthetic{extension}"
            source.write_bytes(b"synthetic document")
            expected_document = object()
            converter = Mock()
            converter.convert.return_value = SimpleNamespace(
                status="success", document=expected_document
            )

            with patch.object(parser, "_get_converter", return_value=converter):
                document = parse_document(source)

        self.assertIs(document, expected_document)
        converter.convert.assert_called_once_with(source, raises_on_error=False)

    def test_합성_HTML을_실제_Docling으로_반복_변환한다(self) -> None:
        html = """<!doctype html>
<html><head><title>Synthetic guide</title></head>
<body><h1>Parser adapter check</h1><p>Generated only for this test.</p></body></html>
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic-guide.html"
            source.write_text(html, encoding="utf-8")

            first = parse_document(source)
            second = parse_document(source)

        self.assertIsInstance(first, DoclingDocument)
        self.assertIs(get_type_hints(parse_document)["return"], DoclingDocument)
        self.assertIn("Parser adapter check", first.export_to_markdown())
        self.assertEqual(first.export_to_markdown(), second.export_to_markdown())
        structure = extract_document_structure(first, source)

        self.assertEqual(structure.source_format, "html")
        self.assertIn("Parser adapter check", [element.text for element in structure.elements])
        self.assertTrue(
            all(element.location.status == "not_applicable" for element in structure.elements)
        )

    def test_제목_절제목_본문을_원문_순서로_추출한다(self) -> None:
        document = DoclingDocument(name="synthetic structure")
        document.add_title("문서 제목")
        document.add_heading("첫 번째 절", level=2)
        document.add_text(label=DocItemLabel.PARAGRAPH, text="  원문 단락\n그대로  ")

        structure = extract_document_structure(document, "synthetic.pdf")

        self.assertEqual(
            [element.kind for element in structure.elements],
            ["document_title", "section_title", "paragraph"],
        )
        self.assertEqual(
            [element.text for element in structure.elements],
            ["문서 제목", "첫 번째 절", "  원문 단락\n그대로  "],
        )
        self.assertEqual(structure.elements[1].level, 2)
        self.assertTrue(all(element.self_ref for element in structure.elements))

    def test_표의_행_열_셀과_병합_범위를_보존한다(self) -> None:
        document = DoclingDocument(name="synthetic table")
        document.add_table(
            data=TableData(
                num_rows=2,
                num_cols=2,
                table_cells=[
                    TableCell(
                        text="항목",
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=2,
                        row_span=1,
                        col_span=2,
                        column_header=True,
                    ),
                    TableCell(
                        text="이름",
                        start_row_offset_idx=1,
                        end_row_offset_idx=2,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                        row_span=1,
                        col_span=1,
                    ),
                    TableCell(
                        text="홍길동",
                        start_row_offset_idx=1,
                        end_row_offset_idx=2,
                        start_col_offset_idx=1,
                        end_col_offset_idx=2,
                        row_span=1,
                        col_span=1,
                    ),
                ],
            )
        )

        structure = extract_document_structure(document, "synthetic.pdf")
        table_element = structure.elements[0]
        self.assertIsNotNone(table_element.table)
        table = table_element.table
        self.assertEqual((table.row_count, table.column_count), (2, 2))
        self.assertEqual([row.cell_indexes for row in table.rows], [(0,), (1, 2)])
        self.assertEqual([cell.text for cell in table.cells], ["항목", "이름", "홍길동"])
        self.assertEqual(table.cells[0].column_span, 2)
        self.assertEqual((table.cells[0].start_column, table.cells[0].end_column), (0, 2))
        self.assertTrue(table.cells[0].column_header)
        self.assertTrue(
            any(
                finding.kind == "table_completeness"
                and finding.self_ref == table_element.self_ref
                for finding in structure.unverified_items
            )
        )

    def test_페이지_provenance와_좌표를_검증된_위치로_보존한다(self) -> None:
        document = DoclingDocument(name="synthetic location")
        provenance = ProvenanceItem(
            page_no=4,
            bbox=BoundingBox(l=10, t=20, r=110, b=40),
            charspan=(2, 10),
        )
        document.add_heading("확인된 제목", level=1, prov=provenance)

        element = extract_document_structure(document, "synthetic.pdf").elements[0]

        self.assertEqual(element.location.status, "verified")
        self.assertEqual(element.location.page_numbers, (4,))
        self.assertEqual(element.location.provenance[0].charspan, (2, 10))
        self.assertEqual(
            element.location.provenance[0].bbox,
            parser.DocumentBoundingBox(10.0, 20.0, 110.0, 40.0, "TOPLEFT"),
        )

    def test_HTML은_페이지_위치를_적용하지_않는다(self) -> None:
        document = DoclingDocument(name="synthetic HTML")
        document.add_text(
            label=DocItemLabel.PARAGRAPH,
            text="HTML 문단",
            prov=ProvenanceItem(
                page_no=1,
                bbox=BoundingBox(l=0, t=0, r=10, b=10),
                charspan=(0, 8),
            ),
        )

        element = extract_document_structure(document, "synthetic.html").elements[0]

        self.assertEqual(element.location.status, "not_applicable")
        self.assertEqual(element.location.page_numbers, ())
        self.assertEqual(element.location.provenance[0].page_no, 1)

    def test_위치_정보가_없으면_미검증으로_표시한다(self) -> None:
        document = DoclingDocument(name="synthetic missing provenance")
        document.add_text(label=DocItemLabel.PARAGRAPH, text="위치 정보 없음")

        structure = extract_document_structure(document, "synthetic.pdf")

        self.assertEqual(structure.elements[0].location.status, "unverified")
        self.assertEqual(structure.elements[0].location.page_numbers, ())
        self.assertEqual(structure.unverified_items[0].kind, "location")
        self.assertEqual(structure.unverified_items[0].self_ref, structure.elements[0].self_ref)

    def test_구조_추출은_반복해도_같은_결과를_반환한다(self) -> None:
        document = DoclingDocument(name="synthetic repeat")
        document.add_title("반복 검증")
        document.add_text(label=DocItemLabel.TEXT, text="같은 결과")

        first = extract_document_structure(document, "synthetic.docx")
        second = extract_document_structure(document, "synthetic.docx")

        self.assertEqual(first, second)

    def test_PDF_경로를_Docling에_전달한다(self) -> None:
        self._assert_mocked_format(".pdf")

    def test_DOCX_경로를_Docling에_전달한다(self) -> None:
        self._assert_mocked_format(".docx")

    def test_없는_파일은_별도_오류로_처리한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.html"

            with self.assertRaises(FileNotFoundError):
                parse_document(source)

    def test_미지원_확장자는_별도_오류로_처리한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            source.write_text("synthetic", encoding="utf-8")

            with self.assertRaises(UnsupportedDocumentFormatError):
                parse_document(source)

    def test_읽을_수_없는_파일은_별도_오류로_처리한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.html"
            source.write_text("synthetic", encoding="utf-8")

            with (
                patch.object(Path, "open", side_effect=PermissionError("denied")),
                patch.object(parser, "_get_converter") as get_converter,
            ):
                with self.assertRaises(DocumentReadError):
                    parse_document(source)

            get_converter.assert_not_called()

    def test_실패_상태의_Docling_결과를_오류로_처리한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.html"
            source.write_text("synthetic", encoding="utf-8")
            converter = Mock()
            converter.convert.return_value = SimpleNamespace(
                status=SimpleNamespace(value="failure"), document=object()
            )

            with patch.object(parser, "_get_converter", return_value=converter):
                with self.assertRaises(DocumentConversionError):
                    parse_document(source)

    def test_Docling_예외를_변환_오류로_감싼다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.html"
            source.write_text("synthetic", encoding="utf-8")
            converter = Mock()
            converter.convert.side_effect = RuntimeError("synthetic conversion failure")

            with patch.object(parser, "_get_converter", return_value=converter):
                with self.assertRaises(DocumentConversionError) as context:
                    parse_document(source)

        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_변환기_인스턴스를_재사용한다(self) -> None:
        converter = object()
        parser._get_converter.cache_clear()
        try:
            with patch.object(
                parser, "_create_converter", return_value=converter
            ) as create_converter:
                first = parser._get_converter()
                second = parser._get_converter()

            self.assertIs(first, second)
            create_converter.assert_called_once_with()
        finally:
            parser._get_converter.cache_clear()

    def test_모듈_가져오기는_Docling_변환이나_DB를_초기화하지_않는다(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "isolated_rag_parser_import", Path(parser.__file__)
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        isolated_parser = importlib.util.module_from_spec(spec)
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "docling" or name.startswith("docling."):
                raise AssertionError("The Docling converter must load only on request")
            if name == "sqlalchemy" or name.startswith("sqlalchemy."):
                raise AssertionError("Parser import must not load database code")
            return original_import(name, *args, **kwargs)

        sys.modules[spec.name] = isolated_parser
        try:
            with patch.object(builtins, "__import__", side_effect=guarded_import):
                spec.loader.exec_module(isolated_parser)
        finally:
            sys.modules.pop(spec.name, None)

        self.assertEqual(isolated_parser._get_converter.cache_info().currsize, 0)

    def test_CLI_파일_인자로_유효한_JSON을_출력한다(self) -> None:
        html = """<!doctype html><html><body>
<h1>CLI 구조 확인</h1><h2>제목</h2><p>본문</p>
<table><tr><th>이름</th></tr><tr><td>홍길동</td></tr></table>
</body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cli-guide.html"
            source.write_text(html, encoding="utf-8")
            stdout, stderr = StringIO(), StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = rag_cli.main(["--file", str(source)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        self.assertEqual(payload["input_file"], str(source))
        self.assertTrue(payload["success"])
        self.assertGreater(payload["element_count"], 0)
        self.assertTrue(payload["elements"])
        self.assertTrue(
            all(
                element["location"]["status"] == "not_applicable"
                for element in payload["elements"]
            )
        )

    def test_파일_경로가_없거나_비어_있으면_사용법_오류를_낸다(self) -> None:
        for argv in ([], ["--file"]):
            stderr = StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as context:
                rag_cli.main(argv)
            self.assertEqual(context.exception.code, 2)
            self.assertIn("usage:", stderr.getvalue())

    def test_CLI에서_없는_파일은_종료_코드_2를_반환한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.html"
            stdout, stderr = StringIO(), StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = rag_cli.main(["--file", str(source)])

        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("문서 파일이 없습니다", stderr.getvalue())

    def test_CLI에서_미지원_형식은_종료_코드_2를_반환한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            source.write_text("synthetic", encoding="utf-8")
            stdout, stderr = StringIO(), StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = rag_cli.main(["--file", str(source)])

        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("지원하지 않는 문서 형식", stderr.getvalue())

    def test_CLI에서_변환_오류는_종료_코드_1을_반환한다(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(rag_cli, "parse_document", side_effect=DocumentConversionError("변환 실패")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = rag_cli.main(["--file", "broken.pdf"])

        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("문서 파싱에 실패했습니다", stderr.getvalue())

    def test_CLI에서_읽기_오류는_종료_코드_2를_반환한다(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(rag_cli, "parse_document", side_effect=DocumentReadError("읽기 실패")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = rag_cli.main(["--file", "unreadable.pdf"])

        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("읽기 실패", stderr.getvalue())

    def test_CLI_파일_인자와_기존_서브커맨드를_함께_거부한다(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with (
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as context,
        ):
            rag_cli.main(["--file", "guide.html", "status"])

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("함께 사용할 수 없습니다", stderr.getvalue())

    def test_기존_status_명령_출력을_유지한다(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = rag_cli.main(["status"])

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "package": "starter-rag",
                "status": "contract-only",
                "searchImplemented": False,
                "ingestionImplemented": False,
            },
        )

    def test_기존_validate_search_명령_출력을_유지한다(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = rag_cli.main(["validate-search", "--query", "상속 포기"])

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {"valid": True, "query": "상속 포기", "topK": 3},
        )

    def test_CLI_모듈_가져오기는_파싱이나_DB_초기화를_하지_않는다(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "isolated_rag_cli_import", Path(rag_cli.__file__)
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        isolated_cli = importlib.util.module_from_spec(spec)
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "docling" or name.startswith("docling."):
                raise AssertionError("CLI import must not load Docling")
            if name == "sqlalchemy" or name.startswith("sqlalchemy."):
                raise AssertionError("CLI import must not load database code")
            return original_import(name, *args, **kwargs)

        sys.modules[spec.name] = isolated_cli
        try:
            with (
                patch.object(builtins, "__import__", side_effect=guarded_import),
                patch.object(parser, "_get_converter") as get_converter,
            ):
                spec.loader.exec_module(isolated_cli)
                get_converter.assert_not_called()
        finally:
            sys.modules.pop(spec.name, None)


if __name__ == "__main__":
    unittest.main()
