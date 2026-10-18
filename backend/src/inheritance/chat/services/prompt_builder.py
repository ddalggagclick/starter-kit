# 담당: [B] | 책임: 질문과 허용된 근거를 모델 중립 메시지로 조립한다.
# PRD: E3 / 스토리 3-3 / 태스크 3-3-4.
# 구현할 기능: RAG 안내자료, MCP 조문, OPEN API 부칙 전문을 서로 구분해 전달한다.
# 완료 기준: 각 근거의 식별자와 출처 정보가 원문 유형에 맞게 유지된다.
# 제한사항: 추가 LLM 호출·외부 법령 조회·질문 원문 영구 저장을 하지 않는다.
# 상태: PRD 태스크 미시작.
"""최종 답변 생성 입력 조립 포트. 구현 코드는 B 담당이 작성한다."""

from __future__ import annotations

from typing import Protocol

from starter_llm.contracts.models import ModelMessage
from starter_rag.contracts.models import Evidence

from inheritance.contracts.law import LawEvidence


class AnswerPromptBuilderPort(Protocol):
    # 질문과 RAG·법령 근거를 ModelMessage로 만들고 근거별 출처 정보를 유지한다.
    def build(
        self, question: str, rag: tuple[Evidence, ...], laws: tuple[LawEvidence, ...]
    ) -> tuple[ModelMessage, ...]: ...
