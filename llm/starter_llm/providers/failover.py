# 담당: [C] | 책임: Gemini -> Groq -> (선택) Ollama 자동 전환(3-2-4, 2026-10-21 변경)을 ModelPort 뒤에서 처리.
# 구현할 기능: 공급자 목록을 순서대로 1회씩 시도, 제한(429) 공급자는 쿨다운 동안 건너뜀.
# 제한사항: 같은 공급자 반복 재시도 금지, 목록 밖 공급자로 전환 금지, 응답 일부 송출 후 전환 금지.
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationChunk, GenerationRequest, GenerationResult
from starter_llm.contracts.ports import ModelPort
from starter_llm.contracts.profiles import FailoverPolicy

# 전환을 일으키는 오류. INVALID_OUTPUT(출력 형식)·UNSUPPORTED·CANCELLED는 전환하지 않는다.
SWITCH_ON = frozenset(
    {ModelErrorCode.RATE_LIMIT, ModelErrorCode.UNAVAILABLE, ModelErrorCode.TIMEOUT}
)


class FailoverModel:
    """ports를 순서대로 공급자별 1회씩 시도한다. 모두 실패하면 오류를 올린다."""

    def __init__(
        self,
        ports: Sequence[ModelPort],
        policy: FailoverPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if len(ports) < 2:
            raise ValueError("failover needs at least two providers")
        self._ports = tuple(ports)
        self._policy = policy or FailoverPolicy()
        self._clock = clock
        self._skip_until = [0.0] * len(self._ports)

    def _order(self) -> list[int]:
        """쿨다운 중인 공급자는 건너뛴다. 단 마지막 공급자는 항상 시도 대상에 남긴다."""
        now = self._clock()
        last = len(self._ports) - 1
        return [i for i in range(len(self._ports)) if i == last or now >= self._skip_until[i]]

    def _note(self, index: int, err: ModelError) -> None:
        if err.code is ModelErrorCode.RATE_LIMIT:
            self._skip_until[index] = self._clock() + self._policy.cooldown_seconds

    @staticmethod
    def _final(errors: list[ModelError]) -> ModelError:
        # 하나라도 사용량 제한이면 호출 측이 S9로 처리할 수 있게 RATE_LIMIT을 유지한다.
        if any(e.code is ModelErrorCode.RATE_LIMIT for e in errors):
            return ModelError(ModelErrorCode.RATE_LIMIT, errors[-1].request_id, retryable=False)
        return errors[-1]

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        errors: list[ModelError] = []
        for i in self._order():
            try:
                return await self._ports[i].generate(request)
            except ModelError as err:
                if err.code not in SWITCH_ON:
                    raise
                errors.append(err)
                self._note(i, err)
        raise self._final(errors) from None

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]:
        async def iterate() -> AsyncIterator[GenerationChunk]:
            errors: list[ModelError] = []
            for i in self._order():
                sent = False
                try:
                    async for chunk in self._ports[i].stream(request):
                        if chunk.text_delta:
                            sent = True
                        yield chunk
                    return
                except ModelError as err:
                    # 이미 일부를 내보냈다면 이어 붙일 수 없으므로 그대로 실패시킨다.
                    if sent or err.code not in SWITCH_ON:
                        raise
                    errors.append(err)
                    self._note(i, err)
            raise self._final(errors) from None

        return iterate()
