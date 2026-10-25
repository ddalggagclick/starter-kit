# 담당: [C] | 책임: 카카오 스킬 JSON → GuidanceInput 변환 시험 (PRD 1-1-2).
# 코드 경계: 어댑터만 시험한다. 카카오 메시지·체크리스트 규칙은 시험하지 않는다.
# 완료 기준: 정상 변환, 잘못된 값 거부, '모름'이 '아니요'로 바뀌지 않음.
"""JsonKakaoInputAdapter 시험."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

from inheritance.contracts.checklist import GuidanceInput
from inheritance.contracts.domain import InitialAnswers, RiskAnswer
from inheritance.kakao.adapter import JsonKakaoInputAdapter, KakaoInputError


def request(**params):
    base = {
        "relationship": "spouse",
        "deathDate": "2026-09-30",
        "deathDateUnknown": "false",
        "oneStopApplication": "yes",
    }
    base.update(params)
    base = {k: v for k, v in base.items() if v is not None}
    return {"userRequest": {"utterance": "x", "user": {"id": "u"}}, "action": {"params": base}}


class KakaoInputAdapterTest(unittest.TestCase):
    def setUp(self):
        self.adapter = JsonKakaoInputAdapter()

    def test_normal_request_becomes_initial_answers(self):
        result = self.adapter.parse(request())
        self.assertIsInstance(result, GuidanceInput)
        self.assertEqual(result.initial, InitialAnswers("spouse", "2026-09-30", False, "yes"))
        self.assertEqual(result.risks, ())

    def test_unknown_death_date(self):
        result = self.adapter.parse(request(deathDate=None, deathDateUnknown="true"))
        self.assertIsNone(result.initial.death_date)
        self.assertTrue(result.initial.death_date_unknown)

    def test_unknown_is_not_converted_to_no(self):
        result = self.adapter.parse(request(oneStopApplication="unknown", relationship="unknown"))
        self.assertEqual(result.initial.one_stop_application, "unknown")
        self.assertEqual(result.initial.relationship, "unknown")
        risks = json.dumps([{"riskId": "debt", "answer": "unknown"}])
        self.assertEqual(self.adapter.parse(request(risks=risks)).risks, (RiskAnswer("debt", "unknown"),))

    def test_risks_accept_json_string_or_list_and_keep_only_answered(self):
        items = [{"riskId": "debt", "answer": "yes"}, {"riskId": "self_application", "answer": "no"}]
        a = self.adapter.parse(request(risks=json.dumps(items))).risks
        b = self.adapter.parse(request(risks=items)).risks
        self.assertEqual(a, b)
        self.assertEqual([r.risk_id for r in a], ["debt", "self_application"])

    def test_missing_risks_means_no_answer_not_no(self):
        for value in (None, "", "[]"):
            self.assertEqual(self.adapter.parse(request(risks=value)).risks, ())

    def test_invalid_values_are_rejected_with_field_name_only(self):
        cases = {
            "relationship": request(relationship="cousin"),
            "oneStopApplication": request(oneStopApplication="maybe"),
            "deathDate": request(deathDate="2026-13-01"),
            "deathDateUnknown": request(deathDateUnknown="maybe"),
        }
        for field, req in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(KakaoInputError) as ctx:
                    self.adapter.parse(req)
                self.assertEqual(ctx.exception.field, field)
                self.assertNotIn("cousin", str(ctx.exception))

    def test_missing_fields_are_rejected(self):
        for name in ("relationship", "oneStopApplication", "deathDateUnknown"):
            with self.subTest(name=name), self.assertRaises(KakaoInputError):
                self.adapter.parse(request(**{name: None}))
        with self.assertRaises(KakaoInputError):
            self.adapter.parse({"userRequest": {}})
        with self.assertRaises(KakaoInputError):
            self.adapter.parse({"action": {"params": "x"}})

    def test_date_rules(self):
        with self.assertRaises(KakaoInputError):  # 날짜와 모름 표시가 서로 맞지 않음
            self.adapter.parse(request(deathDate="2026-09-30", deathDateUnknown="true"))
        with self.assertRaises(KakaoInputError):  # 날짜 없는데 모름 아님
            self.adapter.parse(request(deathDate=None, deathDateUnknown="false"))
        with self.assertRaises(KakaoInputError):  # 미래 날짜
            self.adapter.parse(request(deathDate="2999-01-01"))
        with self.assertRaises(KakaoInputError):  # YYYY-MM-DD 아님
            self.adapter.parse(request(deathDate="20260930"))

    def test_invalid_risks_are_rejected(self):
        bad = [
            "not json",
            json.dumps([{"riskId": "tax", "answer": "yes"}]),
            json.dumps([{"riskId": "debt", "answer": "maybe"}]),
            json.dumps([{"riskId": "debt", "answer": "yes"}, {"riskId": "debt", "answer": "no"}]),
            json.dumps([{"riskId": "debt"}]),
            json.dumps({"riskId": "debt", "answer": "yes"}),
            json.dumps([{"riskId": r, "answer": "yes"} for r in ("debt", "property_disposal", "self_application", "debt")]),
        ]
        for risks in bad:
            with self.subTest(risks=risks), self.assertRaises(KakaoInputError):
                self.adapter.parse(request(risks=risks))

    def test_raw_kakao_json_is_not_in_result(self):
        result = self.adapter.parse(request())
        self.assertNotIn("userRequest", repr(result))


if __name__ == "__main__":
    unittest.main()
