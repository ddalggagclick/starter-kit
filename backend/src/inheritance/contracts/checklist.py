# 담당: [B] | 책임: 체크리스트 추천 제공자/카카오 소비자 공유 입력 경계
# 구현할 기능: 추천 입력 DTO 및 ChecklistService.recommend 공통 함수 시그니처 고정
# 코드 경계: 추천 규칙/HTTP JSON/카카오 JSON 변환은 이 파일에서 구현하지 않는다.
# 완료 기준: B와 C가 같은 RecommendationInput/RecommendationResult로 Fake 계약 테스트 통과.
"""B 담당 추천 제공자와 C 카카오 소비자의 공개 내부 계약."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inheritance.contracts.domain import InitialAnswers, RecommendationResult, RiskAnswer


@dataclass(frozen=True)
class RecommendationInput:
    initial: InitialAnswers
    risks: tuple[RiskAnswer, ...] = ()

    def __post_init__(self) -> None:
        if len(self.risks) > 3 or len({r.risk_id for r in self.risks}) != len(self.risks):
            raise ValueError("at most three unique risk answers")


class ChecklistService(Protocol):
    # 초기 답변과 최대 세 개의 위험 답변을 바탕으로 추천 절차와 우선순위를 반환한다.
    def recommend(self, request: RecommendationInput) -> RecommendationResult: ...
