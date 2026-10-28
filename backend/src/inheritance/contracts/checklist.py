# 담당: [B] | 책임: 공통 체크리스트 안내 입력과 서비스 경계
# 구현할 기능: 공통 안내 입력 DTO와 build_guidance 시그니처 정의
# 코드 경계: 안내 규칙과 HTTP·카카오 JSON은 이 파일에서 구현하지 않는다.
# 완료 기준: 초기·위험 입력과 안내 결과 DTO의 경계를 정의한다.
"""B 담당 안내 제공자와 C 카카오 소비자의 공개 내부 계약."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inheritance.contracts.domain import GuidanceResult, InitialAnswers, RiskAnswer


@dataclass(frozen=True)
class GuidanceInput:
    initial: InitialAnswers
    risks: tuple[RiskAnswer, ...] = ()

    def __post_init__(self) -> None:
        if len(self.risks) > 3 or len({r.risk_id for r in self.risks}) != len(self.risks):
            raise ValueError("at most three unique risk answers")


class ChecklistService(Protocol):
    # 입력 답변으로 절차를 선정하거나 순위를 계산하지 않는다.
    def build_guidance(self, request: GuidanceInput) -> GuidanceResult: ...
