# 담당: [C] | 책임: 요청 간 클라이언트 재사용과 채팅 이탈/유휴 정리 경계
# 구현할 기능: 필요한 공급자만 지연 생성, 활성 임대 추적, 300초 무활동 정리, 종료 취소
# 코드 경계: Provider별 HTTP SDK·Ollama keep_alive 구현은 C 담당. B는 ModelPort만 호출한다.
# 완료 기준: 경쟁 최초 생성 1회, 마지막 사용자 이탈, 활성 중 종료 금지, 유휴 300초, 앱 종료 테스트.
"""실제 클라이언트 생성 구현은 공급자 담당 PR; 이것은 수명주기 Port 계약."""

from __future__ import annotations

from typing import Protocol

from starter_llm.contracts.ports import ModelPort

IDLE_CLOSE_SECONDS = 300


class ModelResourceManager(Protocol):
    # 모델 프로필의 클라이언트를 빌려 호출이 끝날 때까지 유지한다.
    async def acquire(self, model_profile: str) -> ModelPort: ...
    # 호출이 끝난 임대를 반환해 활성 사용 수와 마지막 활동 시각을 갱신한다.
    async def release(self, model_profile: str) -> None: ...
    # 활성 임대가 없고 IDLE_CLOSE_SECONDS 이상 유휴한 클라이언트를 정리한다.
    async def close_idle(self, elapsed_idle_seconds: float) -> None: ...
    # 앱 종료 때 대기 중인 유휴 작업을 취소하고 ModelPort 자원을 정리한다.
    async def shutdown(self) -> None: ...


# 수명 정책: 채팅 이탈 시 요청은 즉시 취소한다. 공유 자원은 활성 임대가 없고 마지막 활동 후 300초가 지나면 닫는다.
# Ollama 모델 가중치 언로드는 별도 정책이다.
