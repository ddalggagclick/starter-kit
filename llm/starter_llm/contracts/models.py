# 담당: [C] | 책임: 공급자에 독립적인 LLM 요청·응답 자료형.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (공개 계약 지원)
# 구현할 기능: 메시지, 생성 요청·결과, 스트림 청크의 불변 조건을 검증한다.
# 완료 기준: 호출 측이 LangChain 자료형 없이 ModelPort DTO만 사용한다.
# 제한사항: 외부 서비스 호출과 HTTP 전송 규격을 이 파일에 두지 않는다.
"""[C] LLM 공개 자료형. 구현할 기능: 공급자 무관 메시지·요청·응답 및 스트림 청크 검증.
계약: ModelPort 소비자는 이 객체만 사용하며 LangChain 객체를 import하지 않는다.
완료: 빈 요청·범위 밖 타임아웃(0 이하/300 초과)·청크 종료 값을 거부하고 데이터 계약 테스트 통과.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]
Provider = Literal["gemini", "ollama"]


@dataclass(frozen=True)
class ModelMessage:
    role: Role
    content: str

    def __post_init__(self):
        if not self.content.strip():
            raise ValueError("message content must not be empty")


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[ModelMessage, ...]
    model_profile: str
    request_id: str
    timeout_seconds: float = 30.0  # T4 확정: 기본 30초, 상한 300초

    def __post_init__(self):
        if not self.messages or not self.model_profile or not self.request_id:
            raise ValueError("required model request fields missing")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("model timeout must be >0 and <=300 seconds")


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: Provider
    model: str
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class GenerationChunk:
    text_delta: str
    done: bool = False
