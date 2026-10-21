# 담당: [C] | 책임: Groq 호출을 공개 ModelPort 자료형으로 변환 (3-2-4 대체 공급자).
# 구현할 기능: ChatGroq 응답과 공급자 오류를 공개 계약으로 변환한다.
# 제한사항: 자체 재시도를 하지 않는다(max_retries=0). Gemini와 별도 키(GROQ_API_KEY)만 사용한다.
from __future__ import annotations

from typing import Any

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.providers._base import LangChainModel


def create_groq(
    model: str, api_key: str, chat: Any | None = None, request_id: str = "init"
) -> LangChainModel:
    """chat을 넘기면(테스트용) 외부 호출 없이 그 객체를 쓴다."""
    if chat is None:
        if not api_key.strip():
            raise ModelError(ModelErrorCode.UNAVAILABLE, request_id)  # 키 없음: 호출 전에 거부
        from langchain_groq import ChatGroq

        chat = ChatGroq(model=model, api_key=api_key, max_retries=0, temperature=0)
    return LangChainModel(chat, provider="groq", model=model)
