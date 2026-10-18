# 담당: [B] | 책임: 질문 분류 AI가 반환하는 검색 경로 및 법령 검색 힌트의 불변 계약
# 구현할 기능: RAG/LAW/BOTH 라우팅 결과 타입과 모델 출력 검증 경계
# 코드 경계: 법령ID·MST·공포번호는 모델 추측값을 신뢰하지 않으며 law/에서 공식 조회한다.
# 완료 기준: 분류 결과 형식 오류/모호한 결과 검증, 후속 검색 제공자 Fake 테스트 통과.
"""분류 LLM 1회 + 공식 검색 + 답변 생성 LLM 1회. API URL은 소유하지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

RouteKind = Literal["RAG", "LAW", "BOTH"]


@dataclass(frozen=True)
class RouteDecision:
    route: RouteKind
    needs_addenda: bool = False
    law_names: tuple[str, ...] = ()
    article_numbers: tuple[str, ...] = ()
    reference_date: str | None = None

    def __post_init__(self) -> None:
        if self.route not in ("RAG", "LAW", "BOTH"):
            raise ValueError("invalid route")
        if any(not x.strip() for x in self.law_names + self.article_numbers):
            raise ValueError("empty law hint")


class QuestionRouterPort(Protocol):
    # 질문을 RAG·법령 검색 경로로 분류한다. 법령 힌트는 공식 조회로 검증해야 한다.
    async def classify(self, question: str) -> RouteDecision: ...
