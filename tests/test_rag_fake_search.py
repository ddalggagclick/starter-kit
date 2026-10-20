"""RAG의 품질 검증 이전 모의 SearchPort 동작을 확인한다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from starter_rag.retrieval.fake_search import make_fixed_evidence


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


if __name__ == "__main__":
    unittest.main()
