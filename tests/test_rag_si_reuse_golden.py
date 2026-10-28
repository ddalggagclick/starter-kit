"""실업인정 도메인 재사용성 평가 자료의 승인 범위와 라벨 무결성 검사."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class SIReuseGoldenTests(unittest.TestCase):
    def test_승인된_14문항과_근거_라벨_수를_유지한다(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "rag"
            / "evaluation"
            / "si_rag_reuse_golden_20261025.json"
        )
        dataset = json.loads(path.read_text(encoding="utf-8"))
        questions = dataset["queries"]
        approved = [
            question
            for question in questions
            if question["label_status"] == "user_approved_ai_reviewed_evidence_ids"
        ]

        self.assertEqual(len(questions), 16)
        self.assertEqual(len(approved), 14)
        self.assertEqual(sum(len(question["gold_evidence_ids"]) for question in approved), 31)
        self.assertEqual(
            len(
                {
                    evidence_id
                    for question in approved
                    for evidence_id in question["gold_evidence_ids"]
                }
            ),
            29,
        )
        self.assertTrue(
            all(
                question["gold_evidence_ids"] == question["human_approved_evidence_ids"]
                for question in approved
            )
        )

    def test_모호한_두_문항은_검색평가에서_제외한다(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "rag"
            / "evaluation"
            / "si_rag_reuse_golden_20261025.json"
        )
        dataset = json.loads(path.read_text(encoding="utf-8"))
        excluded = [
            question
            for question in dataset["queries"]
            if question["label_status"]
            == "excluded_ambiguous_employment_type_not_approved_for_scoring"
        ]

        self.assertEqual({question["query_id"] for question in excluded}, {"SI01-01", "SI01-04"})
        self.assertTrue(all(not question["gold_evidence_ids"] for question in excluded))
