# 담당: [B] | 책임: [C] 카카오→웹 상태 인계의 내부 계약. 구현할 기능: 최소값 전달/단기 일회용 토큰 결과.
# 구현할 기능: Port/DTO의 입력 불변식과 정상·오류 동작을 계약 테스트로 확인.
# 코드 경계: 외부 서비스 호출/HTTP wire 상세를 이 파일에 구현하지 않는다.
# 완료 기준: Python 3.13 표준 라이브러리 계약 테스트 통과.
"""[C] 카카오→웹 상태 인계의 내부 계약. 구현할 기능: 최소값 전달/단기 일회용 토큰 결과.
경계: URL에 카카오 ID·질문 원문을 넣지 않고, 토큰은 DB에 해시로만 저장한다.
완료: 만료/소비됨/무효를 웹에서 동일한 일반 실패로 표현한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from inheritance.contracts.domain import InitialAnswers, RiskAnswer


@dataclass(frozen=True)
class HandoffPayload:
    initial: InitialAnswers
    risks: tuple[RiskAnswer, ...] = ()


@dataclass(frozen=True)
class HandoffExchange:
    status: Literal["ok", "invalid_or_expired"]
    payload: HandoffPayload | None = None

    def __post_init__(self):
        if (self.status == "ok") != (self.payload is not None):
            raise ValueError("successful handoff must include payload and failure must not")
