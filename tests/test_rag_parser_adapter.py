from __future__ import annotations

import builtins
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from docling_core.types.doc import DoclingDocument

from starter_rag.ingestion import parser
from starter_rag.ingestion.parser import (
    DocumentConversionError,
    DocumentReadError,
    UnsupportedDocumentFormatError,
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

    def test_synthetic_html_is_converted_by_docling_and_repeats_stably(self) -> None:
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

    def test_pdf_path_is_sent_to_docling(self) -> None:
        self._assert_mocked_format(".pdf")

    def test_docx_path_is_sent_to_docling(self) -> None:
        self._assert_mocked_format(".docx")

    def test_missing_file_has_a_distinct_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.html"

            with self.assertRaises(FileNotFoundError):
                parse_document(source)

    def test_unsupported_extension_has_a_distinct_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            source.write_text("synthetic", encoding="utf-8")

            with self.assertRaises(UnsupportedDocumentFormatError):
                parse_document(source)

    def test_unreadable_file_has_a_distinct_error(self) -> None:
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

    def test_non_success_docling_status_is_an_error(self) -> None:
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

    def test_docling_exception_is_wrapped_as_conversion_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.html"
            source.write_text("synthetic", encoding="utf-8")
            converter = Mock()
            converter.convert.side_effect = RuntimeError("synthetic conversion failure")

            with patch.object(parser, "_get_converter", return_value=converter):
                with self.assertRaises(DocumentConversionError) as context:
                    parse_document(source)

        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_converter_instance_is_reused(self) -> None:
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

    def test_module_import_does_not_load_docling_or_database(self) -> None:
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

        with patch.object(builtins, "__import__", side_effect=guarded_import):
            spec.loader.exec_module(isolated_parser)

        self.assertEqual(isolated_parser._get_converter.cache_info().currsize, 0)


if __name__ == "__main__":
    unittest.main()
