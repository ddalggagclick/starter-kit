# 담당: [C] | 책임: LLM 공급자에 공통으로 적용할 ModelPort 계약.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (공개 계약 지원)
# 구현할 기능: 단건 비동기 생성과 비동기 청크 스트림의 호출 형태를 고정한다.
# 완료 기준: Backend 호출 측은 이 Protocol과 공개 DTO만 사용한다.
# 제한사항: LangChain·공급자 SDK 타입을 Port 경계에 노출하지 않는다.
"""[C] LLM Port 계약. 구현할 기능: 단건 비동기 생성과 비동기 청크 스트림.
입력: 공급자 중립 GenerationRequest / 출력: GenerationResult 또는 GenerationChunk.
경계: 구현 클래스는 providers/runtime에 두고 호출측은 이 Protocol만 import.
완료: Gemini/Ollama/FakeModel이 동일 시그니처를 따른다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from starter_llm.contracts.models import GenerationChunk, GenerationRequest, GenerationResult


class ModelPort(Protocol):
    # 생성이 끝난 전체 텍스트와 공급자 응답 정보를 한 번에 반환한다.
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
    # 생성 텍스트를 청크로 전달해 상위 서비스가 처리 진행을 조립할 수 있게 한다.
    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]: ...
