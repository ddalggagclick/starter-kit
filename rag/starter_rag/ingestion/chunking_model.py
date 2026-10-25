# 담당: [D] | 책임: Agentic Chunking 전용 모델 설정과 공급자 생성.
# 구현할 기능: RAG 설정을 검증하고 선택한 공급자의 BaseChatModel을 만든다.
# 완료 기준: 모델·인증 오류를 안전하게 처리하고 다른 공급자로 자동 전환하지 않는다.
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from pydantic import ConfigDict, Field

ChunkingProvider = Literal["ollama", "gemini"]
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class ChunkingModelConfigurationError(ValueError):
    pass


class ChunkingModelInitializationError(RuntimeError):
    pass


class _RedactedProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _status_code_value(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 100 <= value <= 599 else None

    candidates = (value, getattr(value, "name", None), getattr(value, "value", None))
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = str(candidate).strip().upper().replace("-", "_")
        if "RESOURCE_EXHAUSTED" in normalized or "TOO_MANY_REQUESTS" in normalized:
            return 429
        if normalized.isdigit() and len(normalized) == 3:
            code = int(normalized)
            return code if 100 <= code <= 599 else None
        match = re.fullmatch(r"HTTP\s+([1-5]\d{2})(?:\s+.*)?", normalized)
        if match:
            return int(match.group(1))
    return None


def _safe_status_from_message(message: str) -> int | None:
    # Extract only recognized status phrases; never retain provider message text.
    normalized = message.upper()
    if re.search(r"\b404\s+MODEL\s+NOT\s+FOUND\b", normalized):
        return 404
    if re.search(r"\bHTTP\s+429\b|\b429\s+RATE\s+LIMITED\b", normalized):
        return 429
    return None


def _initialize_provider_model(
    factory: Callable[..., BaseChatModel],
    *,
    provider: str,
    **kwargs: object,
) -> BaseChatModel:
    try:
        return factory(**kwargs)
    except Exception:  # noqa: BLE001 - provider constructors can include credentials in errors
        initialization_error = ChunkingModelInitializationError(
            f"The configured {provider} chunking model could not be initialized."
        )
    raise initialization_error


class _CredentialRedactingChatModel(BaseChatModel):
    inner_model: BaseChatModel = Field(repr=False, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "credential_redacting"

    @property
    def _identifying_params(self) -> Mapping[str, object]:
        return {}

    def _redact_error(self, error: Exception) -> _RedactedProviderError:
        status_code: int | None = None
        pending: list[object] = [error]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in visited:
                continue
            visited.add(id(current))
            for attribute in ("status_code", "status", "code"):
                code = _status_code_value(getattr(current, attribute, None))
                if code == 429:
                    status_code = code
                    pending.clear()
                    break
                if code is not None and status_code is None:
                    status_code = code
            response = getattr(current, "response", None)
            if response is not None:
                pending.append(response)
            for attribute in ("__cause__", "__context__"):
                related = getattr(current, attribute, None)
                if related is not None:
                    pending.append(related)

        if status_code is None:
            try:
                status_code = _safe_status_from_message(str(error))
            except Exception:  # noqa: BLE001 - do not expose provider error formatting failures
                status_code = None

        if status_code == 404:
            detail = "404 model not found"
        elif status_code is None:
            detail = "[REDACTED]"
        else:
            detail = f"HTTP {status_code}: [REDACTED]"
        return _RedactedProviderError(detail, status_code)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return self.inner_model._generate(
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
        except Exception as error:  # noqa: BLE001 - provider error details can include credentials
            redacted_error = self._redact_error(error)
        raise redacted_error

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await self.inner_model._agenerate(
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
        except Exception as error:  # noqa: BLE001 - provider error details can include credentials
            redacted_error = self._redact_error(error)
        raise redacted_error


@dataclass(frozen=True, slots=True)
class ChunkingModelSettings:
    provider: ChunkingProvider
    model: str
    ollama_base_url: str | None = None
    gemini_api_key: str | None = field(default=None, repr=False)
    ollama_context_tokens: int = 4096


def _validate_ollama_base_url(base_url: str) -> None:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise ChunkingModelConfigurationError(
            "RAG_CHUNKING_OLLAMA_BASE_URL must be a valid HTTP or HTTPS URL."
        ) from None

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ChunkingModelConfigurationError(
            "RAG_CHUNKING_OLLAMA_BASE_URL must be a valid HTTP or HTTPS URL without credentials."
        )


def load_chunking_model_settings(
    environ: Mapping[str, str] | None = None,
) -> ChunkingModelSettings:
    values = os.environ if environ is None else environ
    provider = values.get("RAG_CHUNKING_PROVIDER", "").strip().lower()
    if provider not in {"ollama", "gemini"}:
        raise ChunkingModelConfigurationError(
            "RAG_CHUNKING_PROVIDER must explicitly be set to 'ollama' or 'gemini'."
        )

    model = values.get("RAG_CHUNKING_MODEL", "").strip()
    if not model:
        raise ChunkingModelConfigurationError("RAG_CHUNKING_MODEL must be set.")

    if provider == "gemini":
        if not model.startswith("gemini-"):
            raise ChunkingModelConfigurationError(
                "RAG_CHUNKING_MODEL must be a Gemini model ID when the provider is 'gemini'."
            )
        api_key = values.get("RAG_CHUNKING_GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ChunkingModelConfigurationError(
                "RAG_CHUNKING_GEMINI_API_KEY must be set when the provider is 'gemini'."
            )
        return ChunkingModelSettings(provider="gemini", model=model, gemini_api_key=api_key)

    try:
        context_tokens = int(values.get("RAG_CHUNKING_CONTEXT_TOKENS", "4096"))
    except ValueError:
        raise ChunkingModelConfigurationError(
            "RAG_CHUNKING_CONTEXT_TOKENS must be an integer."
        ) from None
    if context_tokens <= 0:
        raise ChunkingModelConfigurationError("RAG_CHUNKING_CONTEXT_TOKENS must be positive.")

    base_url = values.get("RAG_CHUNKING_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip()
    if not base_url:
        base_url = DEFAULT_OLLAMA_BASE_URL
    _validate_ollama_base_url(base_url)
    return ChunkingModelSettings(
        provider="ollama",
        model=model,
        ollama_base_url=base_url,
        ollama_context_tokens=context_tokens,
    )


def create_chunking_model(
    settings: ChunkingModelSettings,
    *,
    ollama_factory: Callable[..., BaseChatModel] | None = None,
    gemini_factory: Callable[..., BaseChatModel] | None = None,
) -> BaseChatModel:
    if not settings.model.strip():
        raise ChunkingModelConfigurationError("RAG_CHUNKING_MODEL must be set.")

    if settings.provider == "ollama":
        base_url = settings.ollama_base_url or DEFAULT_OLLAMA_BASE_URL
        _validate_ollama_base_url(base_url)
        if ollama_factory is None:
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                raise ChunkingModelInitializationError(
                    "The langchain-ollama provider package is unavailable."
                ) from None
            ollama_factory = ChatOllama
        model = _initialize_provider_model(
            ollama_factory,
            provider="Ollama",
            model=settings.model,
            base_url=base_url,
            temperature=0,
            num_ctx=settings.ollama_context_tokens,
        )
    elif settings.provider == "gemini":
        if not settings.model.startswith("gemini-"):
            raise ChunkingModelConfigurationError(
                "RAG_CHUNKING_MODEL must be a Gemini model ID when the provider is 'gemini'."
            )
        if not settings.gemini_api_key:
            raise ChunkingModelConfigurationError(
                "RAG_CHUNKING_GEMINI_API_KEY must be set when the provider is 'gemini'."
            )
        if gemini_factory is None:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError:
                raise ChunkingModelInitializationError(
                    "The langchain-google-genai provider package is unavailable."
                ) from None
            gemini_factory = ChatGoogleGenerativeAI
        model = _initialize_provider_model(
            gemini_factory,
            provider="Gemini",
            model=settings.model,
            api_key=settings.gemini_api_key,
        )
    else:
        raise ChunkingModelConfigurationError(
            "The configured RAG chunking provider is not supported."
        )

    if not isinstance(model, BaseChatModel):
        raise ChunkingModelInitializationError(
            "The configured chunking model factory did not return a BaseChatModel."
        )
    if settings.provider == "gemini":
        return _CredentialRedactingChatModel(
            inner_model=model,
        )
    return model


def create_chunking_model_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    ollama_factory: Callable[..., BaseChatModel] | None = None,
    gemini_factory: Callable[..., BaseChatModel] | None = None,
) -> BaseChatModel:
    settings = load_chunking_model_settings(environ)
    return create_chunking_model(
        settings,
        ollama_factory=ollama_factory,
        gemini_factory=gemini_factory,
    )
