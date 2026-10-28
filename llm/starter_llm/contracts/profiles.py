# 담당: [C] | 책임: 분류와 답변 생성의 모델 공급자 선택 규칙.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4
# 구현할 기능: Gemini 기본값과 개발자의 명시적 Ollama 선택을 구분한다.
# 완료 기준: 사용량 제한이 발생해도 선택한 공급자를 자동 변경하지 않는다.
# 제한사항: 키·호스트·모델을 승인 없이 바꾸지 않는다.
"""LLM 기본 Gemini. RPM/RPD 제한이면 429(S9) 반환하고 자동 전환하지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["gemini", "ollama"]


@dataclass(frozen=True)
class ModelSelection:
    classification_provider: Provider = "gemini"
    answer_provider: Provider = "gemini"
    auto_fallback: bool = False

    def __post_init__(self) -> None:
        if self.classification_provider not in ("gemini", "ollama") or self.answer_provider not in (
            "gemini",
            "ollama",
        ):
            raise ValueError("unsupported provider")
        if self.auto_fallback:
            raise ValueError("automatic provider fallback is prohibited")
