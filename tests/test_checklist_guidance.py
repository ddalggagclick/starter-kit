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
                "p02": None,
                "p03": "F02",
                "p04": "F03",
                "p05": "F04",
                "p06": None,
                "p07": None,
                "p08": None,
            },
        )
        for notice in result.guidance:
            for link in notice.fallback.links if notice.fallback else ():
                self.assertTrue(link.url.startswith("https://"))
                self.assertTrue(link.browser_checked)

    def test_unapproved_risk_exposure_returns_common_warning_only(self) -> None:
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
            [(r.risk_id, r.answer, r.confirmed) for r in info.answered],
            [
                ("debt", "yes", False),
                ("property_disposal", "no", True),
                ("self_application", "unknown", False),
            ],
        )
        self.assertTrue(all(r.warning_id is None for r in info.answered))

    def test_unanswered_risks_are_not_filled_in(self) -> None:
        info = self.service.build_guidance(GuidanceInput(_initial(True, "no"))).risk_information
        self.assertEqual(info.answered, ())
        self.assertEqual(info.common_warning_id, "W00")

    def test_approved_exposure_table_maps_each_risk_to_its_warning(self) -> None:
        # 노출 조건 값은 시험용 예시다. 실제 조건은 팀 결정 후 RISK_WARNING_EXPOSURE에 넣는다.
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
