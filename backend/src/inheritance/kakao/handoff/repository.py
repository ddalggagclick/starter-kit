# 담당: [C] | 책임: [C] 토큰 상태 원자적 DB 연산
# 구현할 기능: 동시 교환 요청 1건만 성공; 만료 레코드 정리와 인계 자료 수명
# 코드 경계: 카카오→웹 토큰만 다룬다. JWT 로그인 인증 수단으로 사용하지 않는다.
# 완료 기준: 정상·오류·권한/저장 실패 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""Handoff 토큰 저장소 (PRD 1-4-2).

- 운영은 SignedHandoffStore(무상태 서명 토큰)를 쓴다. Vercel에서 서버가 잠들거나 인스턴스가
  바뀌면 메모리 토큰이 사라지기 때문이다 (10/29 팀 결정). 일회용은 같은 인스턴스 안에서만 보장한다.
- InMemoryHandoffStore는 토큰 해시 → 인계 답변을 프로세스 메모리에 두는 이전 방식으로, 계약 시험에서 쓴다.
- PostgreSQL에 저장하지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
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

    # 잠금을 잡은 상태에서만 부른다. 만료된 답변을 지워 메모리에 남기지 않는다.
    def _purge_expired(self, now: float) -> None:
        for key in [k for k, e in self._items.items() if e.expires_at <= now]:
            del self._items[key]

    def issue(self, payload: dict) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            self._items[self._key(token)] = _Entry(payload, now + self._ttl)
        return token

    # 확인과 삭제를 잠금 안에서 한 번에 한다. 동시에 두 요청이 와도 하나만 꺼낸다.
    def consume(self, token: str) -> dict | None:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            entry = self._items.pop(self._key(token), None)
            return entry.payload if entry is not None else None

    # 발급·교환 요청이 없는 동안에도 만료 답변을 지울 수 있도록 주기 작업에서 부른다.
    def purge_expired(self) -> None:
        with self._lock:
            self._purge_expired(self._clock())

    def __len__(self) -> int:
        return len(self._items)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SignedHandoffStore:
    """서버 메모리에 토큰을 저장하지 않는 무상태 토큰 (10/29 팀 결정).

    토큰 = base64(답변·만료시각) + "." + 서명(HMAC-SHA256). 서버가 잠들거나 인스턴스가 바뀌어도
    같은 키만 있으면 교환할 수 있다. 서명은 변조를 막을 뿐 내용을 숨기지 않는다.
    관계·사망일·위험 답변이 URL에서 읽히므로 암호화는 후속 과제로 남긴다.
    일회용은 '같은 인스턴스 안에서만' 보장한다(사용한 토큰 해시를 만료 때까지 메모리에 기억).
    인스턴스가 바뀌면 10분 안에는 다시 쓸 수 있다.
    """

    def __init__(
        self,
        key: str | None = None,
        ttl: int = HANDOFF_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._key = key
        self._ttl = ttl
        self._clock = clock
        self._used: dict[str, float] = {}
        self._lock = threading.Lock()

    def _signing_key(self) -> bytes:
        # 카카오 서버와 나눠 쓰는 HANDOFF_SERVER_SECRET은 서명 키로 쓰지 않는다 (키 분리).
        key = self._key or os.environ.get("HANDOFF_HASH_KEY", "")
        if not key:
            raise ValueError("HANDOFF_HASH_KEY가 설정되지 않았습니다")
        return key.encode()

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._signing_key(), body.encode(), hashlib.sha256).digest())

    def issue(self, payload: dict) -> str:
        expires = int(self._clock() + self._ttl)
        raw = json.dumps({"p": payload, "x": expires}, separators=(",", ":"), ensure_ascii=False)
        body = _b64(raw.encode())
        return f"{body}.{self._sign(body)}"

    def consume(self, token: str) -> dict | None:
        try:
            body, sig = token.split(".", 1)
            if not hmac.compare_digest(sig.encode(), self._sign(body).encode()):
                return None
            data = json.loads(_unb64(body))
            expires = float(data["x"])
            payload = data["p"]
        # base64·JSON 디코딩 오류는 ValueError에 속한다.
        except (ValueError, KeyError, TypeError):
            return None
        now = self._clock()
        if expires <= now or not isinstance(payload, dict):
            return None
        used_key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            self._purge_used(now)
            if used_key in self._used:
                return None
            self._used[used_key] = expires
        return payload

    def _purge_used(self, now: float) -> None:
        for key in [k for k, exp in self._used.items() if exp <= now]:
            del self._used[key]

    def purge_expired(self) -> None:
        with self._lock:
            self._purge_used(self._clock())

    def __len__(self) -> int:
        return len(self._used)
