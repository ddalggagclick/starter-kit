# 담당: [B] | 책임: 채팅 결과의 안전 상태를 분류한다.
# PRD: E3 / 스토리 3-5 / 태스크 3-5-3.
# 구현할 기능: 기술 오류를 S6, 근거 부족을 S7, 사용자·공급자 제한을 S9로 구분한다.
# 완료 기준: 미검증 본문은 공개하지 않고 각 상태를 올바른 화면 결과로 전달한다.
# 제한사항: 근거 ID 검증은 CitationValidator 책임이다. 법률 효력을 판단하지 않는다.
# 상태: PRD 태스크 미시작.
"""모델·근거 조회 실패를 S6/S7/S9와 오류 코드로 바꾼다 (10/21 김선 님과 확정)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from starter_llm.contracts.errors import ModelErrorCode

from inheritance.contracts.chat import AnswerStatus
from inheritance.core.errors import HTTP_STATUS, ErrorCode

ModelStage = Literal["classify", "answer"]
SafetyAction = Literal["outcome", "continue_as_both", "drop"]

SAFETY_STATE: dict[AnswerStatus, str] = {
    "technical_error": "S6",
    "abstained": "S7",
    "limited": "S9",
}


@dataclass(frozen=True)
class SafetyDecision:
    # outcome: status로 끝낸다 / continue_as_both: 분류 실패를 BOTH로 보고 계속 / drop: 결과를 보내지 않는다.
    action: SafetyAction
    status: AnswerStatus | None = None
    # S6·S9의 HTTP 오류 코드. S7은 오류가 아니라 HTTP 200 유보 결과라 None이다.
    error_code: ErrorCode | None = None

    @property
    def http_status(self) -> int | None:
        if self.error_code is not None:
            return HTTP_STATUS[self.error_code]
        return 200 if self.status == "abstained" else None


ABSTAINED = SafetyDecision("outcome", "abstained")
# 법령 조회 unavailable·검색 예외도 공급자 장애와 같은 S6 503으로 본다.
SOURCE_UNAVAILABLE = SafetyDecision("outcome", "technical_error", ErrorCode.PROVIDER_UNAVAILABLE)

_BY_CODE: dict[ModelErrorCode, SafetyDecision] = {
    ModelErrorCode.RATE_LIMIT: SafetyDecision("outcome", "limited", ErrorCode.PROVIDER_RATE_LIMIT),
    ModelErrorCode.TIMEOUT: SafetyDecision(
        "outcome", "technical_error", ErrorCode.PROVIDER_TIMEOUT
    ),
    ModelErrorCode.UNAVAILABLE: SOURCE_UNAVAILABLE,
    ModelErrorCode.UNSUPPORTED_CAPABILITY: SOURCE_UNAVAILABLE,
    # 취소된 요청은 늦은 결과를 보내지 않는다 (PRD 3-5-2).
    ModelErrorCode.CANCELLED: SafetyDecision("drop"),
}


# 출력 형식 오류는 단계에 따라 다르다: 분류는 BOTH로 계속, 답변은 S7 유보. 같은 답변을 다시 생성하지 않는다.
def classify_model_error(code: ModelErrorCode, stage: ModelStage) -> SafetyDecision:
    if code == ModelErrorCode.INVALID_OUTPUT:
        return SafetyDecision("continue_as_both") if stage == "classify" else ABSTAINED
    return _BY_CODE[code]
