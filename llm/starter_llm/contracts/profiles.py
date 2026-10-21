# 담당: [C] | 책임: 분류와 답변 생성의 모델 공급자 선택 규칙.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4
# 구현할 기능: Gemini 기본값과 개발자의 명시적 Ollama 선택을 구분한다.
# 완료 기준: 사용량 제한이 발생해도 선택한 공급자를 자동 변경하지 않는다.
# 제한사항: 키·호스트·모델을 승인 없이 바꾸지 않는다.
"""LLM 기본 Gemini. 제한·장애 시 Groq, (선택) Ollama 순서로 자동 전환(FailoverPolicy, 3-2-4 변경 2026-10-21).
정해진 순서 밖의 전환은 없다. 모두 실패하면 429(S9) 등 오류를 반환한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["gemini", "groq", "ollama"]


@dataclass(frozen=True)
class ModelSelection:
    classification_provider: Provider = "gemini"
    answer_provider: Provider = "gemini"
    auto_fallback: bool = False

    def __post_init__(self) -> None:
        allowed = (
            "gemini",
            "groq",
            "ollama",
        )  # groq 추가(3-2-4): LLMSettings.selection이 groq를 만들 수 있음
        if self.classification_provider not in allowed or self.answer_provider not in allowed:
            raise ValueError("unsupported provider")
        if self.auto_fallback:
            raise ValueError("automatic provider fallback is prohibited")


@dataclass(frozen=True)
class FailoverPolicy:
    """3-2-4 (2026-10-21 변경): Gemini 기본, 제한·장애 시 Groq, (선택) Ollama 순서로 자동 전환.

    - order: 시도 순서. 첫 공급자는 기본 공급자이고, 같은 공급자는 한 번만 나올 수 있다.
    - ModelSelection의 auto_fallback(허용 목록 밖 임의 전환 금지)과는 별개이며, 이 순서 밖으로는 전환하지 않는다.
    - 요청마다 공급자별로 최대 1회만 시도하고, 같은 공급자를 반복 재시도하지 않는다.
    - 공급자가 제한(429)으로 실패하면 cooldown_seconds 동안 그 공급자를 건너뛴다(마지막 공급자는 제외).
    """

    order: tuple[Provider, ...] = ("gemini", "groq")
    cooldown_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.order or len(set(self.order)) != len(self.order):
            raise ValueError("failover order must be non-empty and unique")
        if any(p not in ("gemini", "groq", "ollama") for p in self.order):
            raise ValueError("unsupported provider in failover order")
        if not 0 <= self.cooldown_seconds <= 3600:
            raise ValueError("cooldown must be between 0 and 3600 seconds")
