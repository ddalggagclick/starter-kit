# 담당: [C] | 책임: [C] 공통 메시지 직렬화
# 구현할 기능: 시스템/사용자 메시지 구조 보존; 법률 도메인 프롬프트는 넣지 않기
# 코드 경계: Provider 선택·실행 정책을 담당한다. 법률·검색 근거 판단을 하지 않는다.
# 완료 기준: Gemini/Ollama/FakeModel과 공통 Port 호출 계약 통과.
"""ModelMessage(공개 DTO) -> LangChain 메시지. 내용은 그대로 전달하고 문구를 덧붙이지 않는다."""

from __future__ import annotations

from collections.abc import Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from starter_llm.contracts.models import ModelMessage

_ROLE_TO_CLASS = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def to_langchain_messages(messages: Iterable[ModelMessage]) -> list[BaseMessage]:
    return [_ROLE_TO_CLASS[m.role](content=m.content) for m in messages]


def chunk_text(content: object) -> str:
    """LangChain 응답 content(문자열 또는 블록 목록)를 평문으로 바꾼다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""
