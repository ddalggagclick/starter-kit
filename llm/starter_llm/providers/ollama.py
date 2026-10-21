# 담당: [C] | 책임: Ollama(로컬) 호출을 공개 ModelPort 자료형으로 변환 (3-2-4 전환 순서의 선택 항목).
# 제한사항: LLM_FAILOVER_PROVIDERS에 ollama를 적었을 때만 쓰인다. 자체 재시도 없음. 키는 없다.
# RAG의 Ollama 설정과 변수 이름을 공유하지 않는다(여기는 LLM_OLLAMA_*).
from __future__ import annotations

from typing import Any

from starter_llm.providers._base import LangChainModel


def create_ollama(model: str, base_url: str, chat: Any | None = None) -> LangChainModel:
    if chat is None:
        from langchain_ollama import ChatOllama

        chat = ChatOllama(model=model, base_url=base_url, temperature=0)
    return LangChainModel(chat, provider="ollama", model=model)
