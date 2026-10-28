# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 공통 8개 절차 안내 규칙 단위 테스트.
# PRD: 1-1-3, 1-2-2, 1-2-4, 2-1-3, 2-2-2, 2-4-2.
# 구현할 기능: 6가지 입력 조합의 카드, 8개 고정 순서, 위험 답변 보존, 수정 후 영향 절차를 확인.
# 완료 기준: Python 3.13 표준 라이브러리 unittest 통과.
"""RuleChecklistService 규칙 테스트. 외부 서비스와 HTTP를 호출하지 않는다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import MappingProxyType

root = Path(__file__).resolve().parents[1]
for x in ["llm", "rag", "backend/src"]:
    sys.path.insert(0, str(root / x))

from inheritance.checklist.rules import (
    CONTENT_VERSION,
    PROCEDURE_ORDER,
    WARNING_TEXTS,
    build_risk_information,
)
from inheritance.checklist.service import RuleChecklistService, changed_procedure_ids
from inheritance.contracts.checklist import ChecklistService, GuidanceInput
from inheritance.contracts.domain import InitialAnswers, RiskAnswer


def _initial(date_known: bool, one_stop: str, relationship: str = "spouse") -> InitialAnswers:
    return InitialAnswers(
        relationship=relationship,
        death_date="2026-10-01" if date_known else None,
        death_date_unknown=not date_known,
        one_stop_application=one_stop,
    )


def _cards(result) -> dict[str, str | None]:
    return {notice.procedure_id: notice.card_id for notice in result.guidance}


class ChecklistGuidanceRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RuleChecklistService()

    def test_service_satisfies_checklist_port(self) -> None:
        port: ChecklistService = self.service
        self.assertTrue(callable(port.build_guidance))

    def test_six_baseline_combinations_match_q98_cards(self) -> None:
        # Q98 8.1 T01~T06: 사망 행정 / 안심상속 / 재산·채무 / 상속포기·한정승인
        expected = {
            (True, "yes"): ("01", "03", "06", "09"),
            (True, "no"): ("01", "04", "07", "09"),
            (True, "unknown"): ("01", "05", "08", "09"),
            (False, "yes"): ("02", "03", "06", "10"),
            (False, "no"): ("02", "04", "07", "10"),
            (False, "unknown"): ("02", "05", "08", "10"),
        }
        for (date_known, one_stop), cards in expected.items():
            with self.subTest(date_known=date_known, one_stop=one_stop):
                result = self.service.build_guidance(GuidanceInput(_initial(date_known, one_stop)))
                got = _cards(result)
                self.assertEqual((got["p01"], got["p03"], got["p04"], got["p05"]), cards)
                self.assertEqual(
                    (got["p02"], got["p06"], got["p07"], got["p08"]), (None, None, None, None)
                )

    def test_all_eight_procedures_in_fixed_order_for_every_input(self) -> None:
        for relationship in ("spouse", "descendant", "ascendant", "sibling", "other", "unknown"):
            with self.subTest(relationship=relationship):
                result = self.service.build_guidance(
                    GuidanceInput(_initial(True, "no", relationship))
                )
                ids = tuple(item.procedure_id for item in result.procedures)
                self.assertEqual(ids, PROCEDURE_ORDER)
                self.assertEqual(
                    tuple(notice.procedure_id for notice in result.guidance), PROCEDURE_ORDER
                )

    def test_relationship_does_not_change_guidance(self) -> None:
        spouse = self.service.build_guidance(GuidanceInput(_initial(True, "yes", "spouse")))
        sibling = self.service.build_guidance(GuidanceInput(_initial(True, "yes", "sibling")))
        self.assertEqual(spouse.guidance, sibling.guidance)

    def test_same_input_gives_same_result_and_content_version(self) -> None:
        request = GuidanceInput(_initial(False, "unknown"), (RiskAnswer("debt", "yes"),))
        first = self.service.build_guidance(request)
        second = self.service.build_guidance(request)
        self.assertEqual(first, second)
        self.assertEqual(first.content_version, CONTENT_VERSION)

    def test_fallbacks_attach_to_matching_procedures(self) -> None:
        result = self.service.build_guidance(GuidanceInput(_initial(True, "yes")))
        fallbacks = {
            notice.procedure_id: notice.fallback.fallback_id if notice.fallback else None
            for notice in result.guidance
        }
        self.assertEqual(
            fallbacks,
            {
                "p01": "F01",
                "p02": "F05",
                "p03": "F02",
                "p04": "F03",
                "p05": "F04",
                "p06": "F06",
                "p07": "F07",
                "p08": "F08",
            },
        )
        for notice in result.guidance:
            for link in notice.fallback.links if notice.fallback else ():
                self.assertTrue(link.url.startswith("https://"))

    def test_source_unit_links_only_from_approved_table(self) -> None:
        # SourceUnit 표(김선, 10/21)의 URL만 연결한다. 값은 브라우저 확인 여부.
        expected = {
            "p02": {},
            "p06": {
                "https://fsc.go.kr/no010101/87657": True,
                "https://fine.fss.or.kr/fine/main/contents.do?menuNo=900209": True,
            },
            "p07": {
                "https://land.seoul.go.kr/land/rtms/findYourLand.do": True,
                "https://kgeop.go.kr/myland/laf/getAncLadFind.do": True,
                "https://portal.scourt.go.kr": True,
            },
            "p08": {"https://m.tworld.co.kr/customer/document": True},
        }
        result = self.service.build_guidance(GuidanceInput(_initial(True, "yes")))
        notices = {notice.procedure_id: notice for notice in result.guidance}
        for procedure_id, links in expected.items():
            with self.subTest(procedure_id=procedure_id):
                got = {
                    link.url: link.browser_checked for link in notices[procedure_id].fallback.links
                }
                self.assertEqual(got, links)
                self.assertIn("공식 링크에서 직접 확인", notices[procedure_id].fallback.text)
        all_urls = " ".join(
            link.url for notice in result.guidance for link in notice.fallback.links
        )
        # 사용하지 않는 Unit(신한은행·위택스)과 K-Geo 공지 페이지는 연결하지 않는다.
        for excluded in ("shinhan", "wetax", "nttId"):
            self.assertNotIn(excluded, all_urls)

    def test_all_links_are_browser_checked(self) -> None:
        result = self.service.build_guidance(GuidanceInput(_initial(True, "yes")))
        for notice in result.guidance:
            for link in notice.fallback.links:
                self.assertTrue(link.browser_checked)

    def test_risk_answers_keep_order_and_follow_b_option_exposure(self) -> None:
        risks = (
            RiskAnswer("self_application", "unknown"),
            RiskAnswer("debt", "yes"),
            RiskAnswer("property_disposal", "no", confirmed=True),
        )
        info = self.service.build_guidance(
            GuidanceInput(_initial(True, "yes"), risks)
        ).risk_information
        self.assertEqual(info.common_warning_id, "W00")
        self.assertEqual(info.common_warning_text, WARNING_TEXTS["W00"])
        self.assertEqual(
            [(r.risk_id, r.answer, r.confirmed, r.warning_id) for r in info.answered],
            [
                ("debt", "yes", False, "W01"),
                ("property_disposal", "no", True, None),
                ("self_application", "unknown", False, "W03"),
            ],
        )

    def test_b_option_shows_warning_on_yes_or_unknown_only(self) -> None:
        # B안(#82): 예·모름 → 해당 경고 + W00, 아니요 → W00만. 세 질문 모두 같은 기준.
        expected = {"debt": "W01", "property_disposal": "W02", "self_application": "W03"}
        for risk_id, warning_id in expected.items():
            for answer, shown in (("yes", True), ("unknown", True), ("no", False)):
                with self.subTest(risk_id=risk_id, answer=answer):
                    info = build_risk_information((RiskAnswer(risk_id, answer),))
                    notice = info.answered[0]
                    self.assertEqual(info.common_warning_id, "W00")
                    self.assertEqual(notice.warning_id, warning_id if shown else None)
                    self.assertEqual(
                        notice.warning_text, WARNING_TEXTS[warning_id] if shown else None
                    )

    def test_empty_exposure_returns_common_warning_only(self) -> None:
        # 노출 조건이 없는 분기는 새 문장 없이 공통 경고만 받는다(PRD 1-2-4).
        info = build_risk_information(
            (RiskAnswer("debt", "yes"), RiskAnswer("self_application", "unknown")),
            MappingProxyType({}),
        )
        self.assertEqual(info.common_warning_id, "W00")
        self.assertTrue(all(r.warning_id is None for r in info.answered))

    def test_unanswered_risks_are_not_filled_in(self) -> None:
        info = self.service.build_guidance(GuidanceInput(_initial(True, "no"))).risk_information
        self.assertEqual(info.answered, ())
        self.assertEqual(info.common_warning_id, "W00")

    def test_approved_exposure_table_maps_each_risk_to_its_warning(self) -> None:
        # 노출 조건 표를 인자로 바꿔 넣을 수 있는지 보는 시험용 예시다(실제 값은 B안).
        exposure = MappingProxyType(
            {
                "debt": frozenset({"yes"}),
                "property_disposal": frozenset({"yes"}),
                "self_application": frozenset({"yes"}),
            }
        )
        info = build_risk_information(
            (
                RiskAnswer("debt", "yes"),
                RiskAnswer("property_disposal", "yes"),
                RiskAnswer("self_application", "no"),
            ),
            exposure,
        )
        self.assertEqual([r.warning_id for r in info.answered], ["W01", "W02", None])
        self.assertEqual(info.answered[0].warning_text, WARNING_TEXTS["W01"])

    def test_changed_procedures_after_answer_edit(self) -> None:
        before = self.service.build_guidance(GuidanceInput(_initial(True, "unknown")))
        after = self.service.build_guidance(GuidanceInput(_initial(True, "yes")))
        self.assertEqual(changed_procedure_ids(before, after), ("p03", "p04"))

        date_edit = self.service.build_guidance(GuidanceInput(_initial(False, "yes")))
        self.assertEqual(changed_procedure_ids(after, date_edit), ("p01", "p05"))
        self.assertEqual(changed_procedure_ids(after, after), ())

    def test_risk_edit_does_not_mark_procedures_changed(self) -> None:
        before = self.service.build_guidance(GuidanceInput(_initial(True, "yes")))
        after = self.service.build_guidance(
            GuidanceInput(_initial(True, "yes"), (RiskAnswer("debt", "unknown"),))
        )
        self.assertEqual(changed_procedure_ids(before, after), ())
        self.assertNotEqual(before.risk_information, after.risk_information)

    def test_rejects_non_guidance_input(self) -> None:
        with self.assertRaises(TypeError):
            self.service.build_guidance({"relationship": "spouse"})


if __name__ == "__main__":
    unittest.main()
