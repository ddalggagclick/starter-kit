# 담당: [C] | 책임: Gemini 호출을 공개 ModelPort 자료형으로 변환.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-1, 3-2-4
# 구현할 기능: 모델 응답과 공급자 오류를 공개 계약으로 변환한다.
# 완료 기준: 분류·생성 호출이 지정된 공급자 설정을 따른다.
# 제한사항: 최종 답변 조립은 Backend 책임이다. 자체 재시도는 없고(max_retries=0), 전환은 failover.py가 맡는다.
from __future__ import annotations

from typing import Any

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.providers._base import LangChainModel


def create_gemini(
    model: str, api_key: str, chat: Any | None = None, request_id: str = "init"
) -> LangChainModel:
    """chat을 넘기면(테스트용) 외부 호출 없이 그 객체를 쓴다."""
    if chat is None:
        if not api_key.strip():
            raise ModelError(ModelErrorCode.UNAVAILABLE, request_id)  # 키 없음: 호출 전에 거부
        from langchain_google_genai import ChatGoogleGenerativeAI

        chat = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            max_retries=0,  # 429·오류에서 자동 재시도 금지
        )
    return LangChainModel(chat, provider="gemini", model=model)
