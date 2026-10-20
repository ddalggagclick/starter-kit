# 담당: [통합] | 책임: 최종 코드 인터페이스 DTO·Port 계약 단위 검사
# 구현할 기능: 체크리스트 안내/분류/법령 다건/부칙 버전/출처 URL/429 불변식 테스트
# 코드 경계: 외부 API·실 브라우저·GPU/DB 호출은 여기서 수행하지 않는다.
# 완료 기준: 공개 DTO와 정책 불변식 검사가 통과한다.
"""내부 인터페이스 동작을 외부 서비스 호출 없이 검사한다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]
for root in ("llm", "rag", "backend/src"):
    sys.path.insert(0, str(ROOT / root))
from inheritance.contracts.chat import AnswerOutcome, AnswerReference
from inheritance.contracts.checklist import ChecklistService, GuidanceInput
from inheritance.contracts.domain import InitialAnswers, RiskAnswer
from inheritance.core.app_ports import AppServicePorts
from inheritance.kakao.adapter import KakaoInputAdapter
from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.contracts.routing import RouteDecision
from inheritance.core.errors import HTTP_STATUS, ErrorCode
from inheritance.law.addenda_contract import AmendmentCandidate, FullAddendum
from starter_llm.contracts.profiles import ModelSelection
from starter_llm.runtime.lifecycle import IDLE_CLOSE_SECONDS


class FinalInterfaceTests(unittest.TestCase):
    def reference(self):
        return AnswerReference(
            "e1",
            "law_article",
            "민법 제1019조",
            "https://www.law.go.kr/official",
            "제1019조",
            "2026-03-17",
        )

    def test_default_is_gemini_and_no_fallback(self):
        self.assertEqual(ModelSelection(), ModelSelection("gemini", "gemini", False))
        with self.assertRaises(ValueError):
            ModelSelection(auto_fallback=True)

    def test_ollama_requires_explicit_override(self):
        self.assertEqual(
            ModelSelection("ollama", "gemini", False).classification_provider, "ollama"
        )

    def test_gemini_limit_code_maps_429(self):
        self.assertEqual(HTTP_STATUS[ErrorCode.PROVIDER_RATE_LIMIT], 429)

    def test_idle_timeout_five_minutes(self):
        self.assertEqual(IDLE_CLOSE_SECONDS, 300)

    def test_route_enums(self):
        self.assertEqual(RouteDecision("LAW").route, "LAW")
        self.assertTrue(RouteDecision("BOTH", needs_addenda=True).needs_addenda)
        with self.assertRaises(ValueError):
            RouteDecision("OTHER")

    def test_router_disallows_blank_hints(self):
        with self.assertRaises(ValueError):
            RouteDecision("LAW", law_names=(" ",))

    def test_guidance_input_reuses_initial_and_risk_answers(self):
        i = InitialAnswers("spouse", None, True, "unknown")
        a = RiskAnswer("debt", "yes")
        self.assertIs(GuidanceInput(i, (a,)).initial, i)
        with self.assertRaises(ValueError):
            GuidanceInput(i, (a, a))

    def test_checklist_and_kakao_share_guidance_input(self):
        self.assertEqual(
            get_type_hints(ChecklistService.build_guidance)["request"], GuidanceInput
        )
        self.assertEqual(get_type_hints(KakaoInputAdapter.parse)["return"], GuidanceInput)

    def test_app_ports_keep_checklist_service(self):
        self.assertIs(get_type_hints(AppServicePorts)["checklist"], ChecklistService)

    def test_answer_reference_has_url_and_location(self):
        r = self.reference()
        self.assertEqual(
            AnswerOutcome("answered", "답변", (r,), "r1").references[0].location, "제1019조"
        )
        with self.assertRaises(ValueError):
            AnswerReference("e", "law_article", "title", "http://invalid", "loc", "2026")

    def test_multi_article_and_addendum(self):
        a = LawEvidence(
            "law:1",
            "article",
            "민법",
            "제1019조",
            "조문 전문",
            "2026-03-17",
            "https://www.law.go.kr",
            "2026-10-18",
            mst="1",
        )
        b = LawEvidence(
            "law:2",
            "addendum",
            "민법",
            "부칙 전문",
            "부칙 원문 전문",
            "2022-12-13",
            "https://www.law.go.kr",
            "2026-10-18",
            mst="245913",
            promulgation_number="19069",
        )
        r = LawLookupResult("verified", (a, b))
        self.assertEqual(len(r.evidence), 2)

    def test_addenda_requires_revision_marker(self):
        with self.assertRaises(ValueError):
            LawEvidence(
                "law:2", "addendum", "민법", "부칙", "text", "2022", "https://www.law.go.kr", "now"
            )

    def test_mcp_addendum_candidate_needs_identity(self):
        with self.assertRaises(ValueError):
            AmendmentCandidate(None, "", "19069", "2022-12-13")
        c = AmendmentCandidate("1001", "245913", "19069", "2022-12-13")
        self.assertEqual(
            FullAddendum(c, "시행일과 적용례 전문", "https://www.law.go.kr").candidate, c
        )

    def test_law_query_requires_question(self):
        with self.assertRaises(ValueError):
            LawQuery("   ")

    def test_url_not_guessed(self):
        with self.assertRaises(ValueError):
            FullAddendum(AmendmentCandidate("1", "2", "3", "2022"), "text", "http://foo")


if __name__ == "__main__":
    unittest.main()
