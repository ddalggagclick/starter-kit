# 담당: [B] | 책임: 체크리스트 추천 유스케이스.
# PRD: E2 / 스토리 2-1, 2-4 / 태스크 2-1-3, 2-4-2.
# 구현할 기능: 입력을 다시 검증하고 공통 추천 규칙을 호출한다. 답변 수정 후 추천을 다시 계산한다.
# 완료 기준: 같은 규칙 함수가 웹과 카카오 입력에 같은 결과를 반환한다.
# 제한사항: HTTP 입력·응답 형식은 API 담당자 승인 전 확정하지 않는다.
# 상태: PRD 태스크 미시작.
"""ChecklistService(I02) 규칙 구현. 카카오와 웹이 같은 인스턴스를 공유한다."""

from __future__ import annotations

from inheritance.checklist.rules import (
    CONTENT_VERSION,
    ProcedureNotice,
    build_procedure_notices,
    build_risk_information,
)
from inheritance.contracts.checklist import GuidanceInput
from inheritance.contracts.domain import GuidanceResult, ProcedureGuidance, ProcedureId


class RuleChecklistService:
    # 같은 입력과 CONTENT_VERSION이면 항상 같은 결과를 낸다. LLM·DB를 호출하지 않는다.
    # 입력 검증은 GuidanceInput·InitialAnswers 생성 시점에 이미 끝나 있어야 한다.
    def build_guidance(self, request: GuidanceInput) -> GuidanceResult:
        if not isinstance(request, GuidanceInput):
            raise TypeError("request must be GuidanceInput")
        notices = build_procedure_notices(request.initial)
        return GuidanceResult(
            procedures=tuple(ProcedureGuidance(notice.procedure_id) for notice in notices),
            guidance=notices,
            risk_information=build_risk_information(request.risks),
            content_version=CONTENT_VERSION,
        )


# 답변 수정 전후 결과를 비교해 안내 문구가 바뀐 절차만 돌려준다(PRD 2-4-2).
# 화면은 이 중 이미 '안내 확인'한 절차에만 재확인 배지를 붙인다. 체크 상태는 바꾸지 않는다.
def changed_procedure_ids(
    previous: GuidanceResult, current: GuidanceResult
) -> tuple[ProcedureId, ...]:
    before = _notices_by_id(previous)
    after = _notices_by_id(current)
    return tuple(
        procedure_id
        for procedure_id, notice in after.items()
        if before.get(procedure_id) != notice or previous.content_version != current.content_version
    )


def _notices_by_id(result: GuidanceResult) -> dict[ProcedureId, ProcedureNotice]:
    if not isinstance(result.guidance, tuple):
        raise TypeError("guidance must come from RuleChecklistService")
    return {notice.procedure_id: notice for notice in result.guidance}
