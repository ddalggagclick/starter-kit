# 담당: [C] | 책임: 설정된 공급자 호출을 ModelPort로 제공.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4 (호출 경계 지원)
# 구현할 기능: 요청 ID, 취소, 예외를 공개 Port 경계에서 일관되게 처리한다.
# 완료 기준: Backend는 공급자별 구현을 알지 않고 ModelPort를 호출한다.
# 제한사항: 법률·검색 근거를 판단하거나 최종 답변을 조립하지 않는다.
"""ModelResourceManager 구현. 프로필(model_profile)별 클라이언트를 처음 쓸 때 한 번만 만들고,
활성 임대가 없고 유휴 300초가 지나면 닫는다. model_profile 값은 'answer' 또는 'classifier'."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from starter_llm.contracts.ports import ModelPort
from starter_llm.providers.factory import create_model
from starter_llm.runtime.lifecycle import IDLE_CLOSE_SECONDS
from starter_llm.runtime.settings import LLMSettings


class ManagedModelResources:
    def __init__(
        self,
        settings: LLMSettings,
        factory: Callable[[LLMSettings, str], ModelPort] = create_model,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._clients: dict[str, ModelPort] = {}
        self._leases: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, model_profile: str) -> ModelPort:
        async with self._lock:  # 동시에 첫 요청이 와도 생성은 1회
            client = self._clients.get(model_profile)
            if client is None:
                client = self._factory(self._settings, model_profile)
                self._clients[model_profile] = client
            self._leases[model_profile] = self._leases.get(model_profile, 0) + 1
            return client

    async def release(self, model_profile: str) -> None:
        async with self._lock:
            count = self._leases.get(model_profile, 0)
            self._leases[model_profile] = max(0, count - 1)

    async def close_idle(self, elapsed_idle_seconds: float) -> None:
        if elapsed_idle_seconds < IDLE_CLOSE_SECONDS:
            return
        async with self._lock:
            for profile in [p for p in self._clients if self._leases.get(p, 0) == 0]:
                await self._close(self._clients.pop(profile))
                self._leases.pop(profile, None)

    async def shutdown(self) -> None:
        async with self._lock:
            for client in self._clients.values():
                await self._close(client)
            self._clients.clear()
            self._leases.clear()

    @staticmethod
    async def _close(client: ModelPort) -> None:
        closer = getattr(client, "aclose", None)
        if closer is not None:
            await closer()
