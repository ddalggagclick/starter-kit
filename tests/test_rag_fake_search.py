"""RAG의 품질 검증 이전 모의 SearchPort 동작을 확인한다."""

from __future__ import annotations

import asyncio
import inspect
import sys
import unittest
from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from starter_rag.contracts.models import SearchRequest, SearchResult
from starter_rag.contracts.ports import SearchPort
from starter_rag.retrieval.fake_search import FakeSearchPort, make_fixed_evidence


class FixedEvidenceTests(unittest.TestCase):
    def test_fixed_evidence_has_required_synthetic_source_metadata(self) -> None:
        evidence = make_fixed_evidence()

        self.assertTrue(evidence.evidence_id)
        self.assertTrue(evidence.text)
        self.assertTrue(evidence.location)
        self.assertTrue(evidence.source.source_id)
        self.assertTrue(evidence.source.title)
        self.assertTrue(evidence.source.url.startswith("https://"))
        self.assertTrue(evidence.source.publisher)
        self.assertTrue(evidence.source.version)
        self.assertIn("synthetic", evidence.evidence_id)
        self.assertIn("합성", evidence.source.title)
        self.assertIn("합성", evidence.source.publisher)
        self.assertIn("example.invalid", evidence.source.url)

    def test_fixed_evidence_is_deterministic(self) -> None:
        self.assertEqual(make_fixed_evidence(), make_fixed_evidence())


class FakeSearchEvidenceTests(unittest.TestCase):
    def test_search_returns_fixed_evidence_as_search_result(self) -> None:
        request = SearchRequest("합성 안내 질문")
        search = FakeSearchPort(scenario="evidence")

        result = asyncio.run(search.search(request))

        self.assertIsInstance(result, SearchResult)
        self.assertEqual(result.evidence, (make_fixed_evidence(),))

    def test_search_method_matches_search_port_signature(self) -> None:
        fake_signature = inspect.signature(FakeSearchPort.search)
        port_signature = inspect.signature(SearchPort.search)
        self.assertEqual(
            tuple(
                (name, parameter.kind)
                for name, parameter in fake_signature.parameters.items()
            ),
            tuple(
                (name, parameter.kind)
                for name, parameter in port_signature.parameters.items()
            ),
        )
        self.assertEqual(
            get_type_hints(FakeSearchPort.search), get_type_hints(SearchPort.search)
        )

    def test_search_respects_request_top_k(self) -> None:
        search = FakeSearchPort(scenario="evidence")

        for top_k in (1, 3, 10):
            with self.subTest(top_k=top_k):
                result = asyncio.run(search.search(SearchRequest("합성 질문", top_k)))
                self.assertLessEqual(len(result.evidence), top_k)


if __name__ == "__main__":
    unittest.main()
