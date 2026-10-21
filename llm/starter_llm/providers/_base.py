# 담당: [C] | 책임: Gemini·Ollama 어댑터가 공유하는 호출·오류 정규화.
# 제한사항: 자동 재시도·공급자 전환을 하지 않는다. 오류 메시지에 프롬프트·키를 넣지 않는다.
from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    Provider,
)
from starter_llm.runtime.prompts import chunk_text, to_langchain_messages


def classify_exception(exc: BaseException, request_id: str) -> ModelError:
    """공급자 예외를 공개 오류 코드로 바꾼다. 429는 재시도 불가(retryable=False)."""
    if isinstance(exc, ModelError):
        return exc
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ModelError(ModelErrorCode.TIMEOUT, request_id, retryable=False)
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if (
        code == 429
        or "resourceexhausted" in name
        or "toomanyrequests" in name
        or "ratelimit" in name
    ):
        return ModelError(ModelErrorCode.RATE_LIMIT, request_id, retryable=False)
    if code in (408, 504) or "timeout" in name or "timed out" in text:
        return ModelError(ModelErrorCode.TIMEOUT, request_id, retryable=False)
    if isinstance(exc, ValueError):
        return ModelError(ModelErrorCode.INVALID_OUTPUT, request_id, retryable=False)
    return ModelError(ModelErrorCode.UNAVAILABLE, request_id, retryable=False)


def _usage(message: Any) -> tuple[int | None, int | None]:
    usage = getattr(message, "usage_metadata", None) or {}
    return usage.get("input_tokens"), usage.get("output_tokens")


class LangChainModel:
    """LangChain 채팅 모델을 ModelPort 모양으로 감싼다. LangChain 타입은 밖으로 나가지 않는다."""

    provider: Provider

    def __init__(self, chat: Any, provider: Provider, model: str) -> None:
        self._chat = chat
        self.provider = provider
        self.model = model

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            msg = await asyncio.wait_for(
                self._chat.ainvoke(to_langchain_messages(request.messages)),
                timeout=request.timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 공급자 예외를 공개 코드로 통일
            raise classify_exception(exc, request.request_id) from None
        text = chunk_text(getattr(msg, "content", ""))
        if not text.strip():
            raise ModelError(ModelErrorCode.INVALID_OUTPUT, request.request_id)
        meta = getattr(msg, "response_metadata", None) or {}
        tin, tout = _usage(msg)
        return GenerationResult(
            text=text,
            provider=self.provider,
            model=self.model,
            finish_reason=meta.get("finish_reason"),
            input_tokens=tin,
            output_tokens=tout,
        )

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]:
        async def iterate() -> AsyncIterator[GenerationChunk]:
            deadline = time.monotonic() + request.timeout_seconds
            source = self._chat.astream(to_langchain_messages(request.messages)).__aiter__()
            sent = False
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        piece = await asyncio.wait_for(source.__anext__(), timeout=remaining)
                    except StopAsyncIteration:
                        break
                    delta = chunk_text(getattr(piece, "content", ""))
                    if delta:
                        sent = True
                        yield GenerationChunk(text_delta=delta)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001
                raise classify_exception(exc, request.request_id) from None
            finally:
                aclose = getattr(source, "aclose", None)
                if aclose is not None:
                    with contextlib.suppress(Exception):  # 정리 중 오류는 무시
                        await aclose()
            if not sent:
                raise ModelError(ModelErrorCode.INVALID_OUTPUT, request.request_id)
            yield GenerationChunk(text_delta="", done=True)

        return iterate()
