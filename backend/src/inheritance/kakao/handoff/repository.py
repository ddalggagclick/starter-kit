# 담당: [C] | 책임: [C] 토큰 상태 원자적 DB 연산
# 구현할 기능: 동시 교환 요청 1건만 성공; 만료 레코드 정리와 인계 자료 수명
# 코드 경계: 카카오→웹 토큰만 다룬다. JWT 로그인 인증 수단으로 사용하지 않는다.
# 완료 기준: 정상·오류·권한/저장 실패 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""토큰 해시 → 인계 답변을 프로세스 메모리에 둔다 (PRD 1-4-2).

- PostgreSQL에 저장하지 않는다. 서버를 재시작하면 쓰지 않은 토큰도 사라진다.
- 메모리를 나눠 쓰지 않도록 서버 프로세스(uvicorn 워커)는 1개로 실행한다.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

HANDOFF_TTL_SECONDS = 600  # 10분 (PRD 1-4)


@dataclass
class _Entry:
    payload: dict
    expires_at: float


class InMemoryHandoffStore:
    def __init__(
        self, ttl: int = HANDOFF_TTL_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._items: dict[str, _Entry] = {}
        # FastAPI는 일반 def 엔드포인트를 스레드 풀에서 돌리므로 스레드 잠금을 쓴다.
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        # 원문 토큰은 보관하지 않고 해시만 키로 쓴다 (tokenHash).
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, payload: dict) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            for key in [k for k, e in self._items.items() if e.expires_at <= now]:
                del self._items[key]
            self._items[self._key(token)] = _Entry(payload, now + self._ttl)
        return token

    # 확인과 삭제를 잠금 안에서 한 번에 한다. 동시에 두 요청이 와도 하나만 꺼낸다.
    def consume(self, token: str) -> dict | None:
        with self._lock:
            entry = self._items.pop(self._key(token), None)
            if entry is None or entry.expires_at <= self._clock():
                return None
            return entry.payload

    def __len__(self) -> int:
        return len(self._items)
