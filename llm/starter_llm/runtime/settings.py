# 담당: [C] | 책임: 공급자 설정과 허용 범위.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4 (설정 경계 지원)
# 구현할 기능: 기본 Gemini와 자동 전환 순서(Groq, 선택 Ollama; 3-2-4, 2026-10-21 변경) 설정을 전달한다.
# 완료 기준: 설정된 공급자와 모델이 요청 실행에 그대로 적용된다.
# 제한사항: API 키를 로그에 남기지 않는다. 자동 전환은 설정한 순서(gemini -> groq -> 선택 ollama) 밖으로 하지 않는다.
"""환경 변수에서 LLM 설정을 읽는다. 이름은 루트 .env.example 기준이다.

LLM_PROVIDER / LLM_MODEL            최종 답변 생성용 기본 공급자 (기본 gemini, groq도 가능)
CLASSIFIER_PROVIDER / CLASSIFIER_MODEL  분류용 (기본 gemini)
LLM_AUTO_FALLBACK                   반드시 false 유지(구 항목). true이면 거부한다.
LLM_FAILOVER_PROVIDERS              자동 전환 순서(쉼표). 기본 groq. 예: groq,ollama / none(전환 끄기)
LLM_FAILOVER_MODEL / CLASSIFIER_FAILOVER_MODEL  Groq 모델 (기본 openai/gpt-oss-120b)
LLM_OLLAMA_BASE_URL / LLM_OLLAMA_MODEL  Ollama(로컬) 사용 시 (기본 http://127.0.0.1:11434, qwen3:4b-instruct)
LLM_FAILOVER_COOLDOWN_SECONDS       제한(429) 뒤 해당 공급자를 건너뛰는 시간(기본 60초)
GEMINI_API_KEY / GROQ_API_KEY       서로 다른 키. 값은 어디에도 출력하지 않는다
RAG의 Ollama 설정과 변수 이름을 공유하지 않는다(LLM 쪽은 LLM_OLLAMA_*, RAG 쪽은 RAG_ 접두 권장).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from starter_llm.contracts.profiles import FailoverPolicy, ModelSelection, Provider

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"  # .env.example 기준 기본값
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"  # Groq 문서의 production 모델(확인한 계정의 모델 목록에 있음)
DEFAULT_OLLAMA_MODEL = "qwen3:4b-instruct"  # .env.example 기준 기본값
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_TRUE = {"1", "true", "yes", "on"}


class SettingsError(ValueError):
    """설정 오류. 메시지에 비밀값을 넣지 않는다."""


@dataclass(frozen=True)
class ProviderTarget:
    provider: Provider
    model: str


@dataclass(frozen=True)
class LLMSettings:
    answer: ProviderTarget
    classifier: ProviderTarget
    gemini_api_key: str = field(default="", repr=False)  # repr·로그에 노출 금지
    groq_api_key: str = field(default="", repr=False)
    failover_answer: tuple[ProviderTarget, ...] = ()  # 기본 다음 순서. 비어 있으면 자동 전환 없음
    failover_classifier: tuple[ProviderTarget, ...] = ()
    ollama_base_url: str = DEFAULT_OLLAMA_URL
    failover_policy: FailoverPolicy = field(default_factory=FailoverPolicy)

    @property
    def selection(self) -> ModelSelection:
        return ModelSelection(
            classification_provider=self.classifier.provider,
            answer_provider=self.answer.provider,
            auto_fallback=False,
        )

    def target_for(self, purpose: str) -> ProviderTarget:
        if purpose == "classifier":
            return self.classifier
        if purpose == "answer":
            return self.answer
        raise SettingsError("purpose must be 'classifier' or 'answer'")

    def failover_for(self, purpose: str) -> tuple[ProviderTarget, ...]:
        return self.failover_classifier if purpose == "classifier" else self.failover_answer

    def chain_for(self, purpose: str) -> tuple[ProviderTarget, ...]:
        """기본 공급자 + 전환 순서 전체."""
        return (self.target_for(purpose), *self.failover_for(purpose))

    def key_for(self, provider: str) -> str:
        if provider == "gemini":
            return self.gemini_api_key
        if provider == "groq":
            return self.groq_api_key
        return ""

    def api_key_configured(self, provider: str = "gemini") -> bool:
        if provider == "ollama":
            return True  # 키가 필요 없다(서버가 떠 있는지는 호출 때 확인)
        return bool(self.key_for(provider).strip())

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        env = os.environ if env is None else env
        if env.get("LLM_AUTO_FALLBACK", "false").strip().lower() in _TRUE:
            raise SettingsError(
                "LLM_AUTO_FALLBACK must be false (automatic fallback is prohibited)"
            )

        def target(provider_key: str, model_key: str) -> ProviderTarget:
            provider = env.get(provider_key, "gemini").strip().lower() or "gemini"
            if provider not in ("gemini", "groq"):
                raise SettingsError(f"{provider_key} must be 'gemini' or 'groq'")
            default = DEFAULT_GEMINI_MODEL if provider == "gemini" else DEFAULT_GROQ_MODEL
            model = env.get(model_key, "").strip() or default
            return ProviderTarget(provider=provider, model=model)  # type: ignore[arg-type]

        answer = target("LLM_PROVIDER", "LLM_MODEL")
        classifier = target("CLASSIFIER_PROVIDER", "CLASSIFIER_MODEL")

        raw = env.get("LLM_FAILOVER_PROVIDERS", "groq").strip().lower() or "groq"
        names = [] if raw == "none" else [x.strip() for x in raw.split(",") if x.strip()]
        if any(n not in ("groq", "ollama") for n in names) or len(set(names)) != len(names):
            raise SettingsError(
                "LLM_FAILOVER_PROVIDERS must be 'none' or a unique list of groq, ollama"
            )
        groq_main = env.get("LLM_FAILOVER_MODEL", "").strip() or DEFAULT_GROQ_MODEL
        groq_cls = env.get("CLASSIFIER_FAILOVER_MODEL", "").strip() or groq_main
        ollama_model = env.get("LLM_OLLAMA_MODEL", "").strip() or DEFAULT_OLLAMA_MODEL

        def chain(primary: ProviderTarget, groq_model: str) -> tuple[ProviderTarget, ...]:
            out = []
            for n in names:
                if n == primary.provider:
                    continue  # 기본 공급자와 같은 곳은 건너뛴다
                out.append(ProviderTarget(n, groq_model if n == "groq" else ollama_model))
            return tuple(out)

        try:
            cooldown = float(env.get("LLM_FAILOVER_COOLDOWN_SECONDS", "60") or 60)
            policy = FailoverPolicy(
                order=(answer.provider, *[n for n in names if n != answer.provider]),
                cooldown_seconds=cooldown,
            )
        except ValueError as exc:
            raise SettingsError(f"failover settings invalid: {exc}") from None

        return cls(
            answer=answer,
            classifier=classifier,
            gemini_api_key=env.get("GEMINI_API_KEY", ""),
            groq_api_key=env.get("GROQ_API_KEY", ""),
            failover_answer=chain(answer, groq_main),
            failover_classifier=chain(classifier, groq_cls),
            ollama_base_url=env.get("LLM_OLLAMA_BASE_URL", "").strip() or DEFAULT_OLLAMA_URL,
            failover_policy=policy,
        )
