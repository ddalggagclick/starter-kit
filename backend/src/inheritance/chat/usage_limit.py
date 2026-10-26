# 담당: [B] | 책임: 비회원 AI 질문 하루 10회·회원 1분 10회 서버 제한.
# PRD: E3 / 태스크 3-7-2, 3-7-3 (openapi A08 429 RATE_LIMITED, result.remainingToday).
# 구현할 기능: 비회원을 접속 IP의 비밀키 해시로 구분해 한국 시간 하루 단위로 센다.
# 완료 기준: 11번째 질문은 스트림을 열기 전에 429 RATE_LIMITED, 로그인 사용자는 제한하지 않는다.
# 제한사항: 원본 IP는 저장·로그하지 않는다. ERD 승인 전이라 메모리에 두며 재시작하면 초기화된다.
"""비회원 하루 제한(2026-10-26 팀 회의 결정: IP 해시).

Gemini 공급자 한도(PROVIDER_RATE_LIMIT, S9)와는 다른 코드(RATE_LIMITED)를 쓴다(3-7-3).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

GUEST_DAILY_LIMIT = 10
_KST = timezone(timedelta(hours=9))


def _kst_day() -> str:
    return datetime.now(UTC).astimezone(_KST).date().isoformat()


class GuestDailyLimiter:
    def __init__(
        self,
        limit: int = GUEST_DAILY_LIMIT,
        hash_key: bytes | None = None,
        today: Callable[[], str] = _kst_day,
    ) -> None:
        self._limit = limit
        # 메모리 저장이라 프로세스마다 새 키여도 된다. 같은 IP라도 서버 밖에서 되돌릴 수 없다.
        self._key = hash_key or secrets.token_bytes(32)
        self._today = today
        self._lock = threading.Lock()
        self._day = ""
        self._counts: dict[str, int] = {}

    def _visitor(self, client_ip: str) -> str:
        return hmac.new(self._key, client_ip.encode(), hashlib.sha256).hexdigest()

    # 한 번 센 뒤 남은 횟수를 돌려준다. 이미 한도에 닿았으면 None(세지 않음).
    def take(self, client_ip: str) -> int | None:
        visitor = self._visitor(client_ip)
        with self._lock:
            day = self._today()
            if day != self._day:
                # 날짜가 바뀌면 지난 기록을 모두 버린다(하루가 지난 해시를 남기지 않는다).
                self._day, self._counts = day, {}
            used = self._counts.get(visitor, 0)
            if used >= self._limit:
                return None
            self._counts[visitor] = used + 1
            return self._limit - used - 1


MEMBER_PER_MINUTE_LIMIT = 10
GUEST_DAILY_REASON = "GUEST_DAILY_LIMIT"
MEMBER_MINUTE_REASON = "MEMBER_MINUTE_LIMIT"


class MemberMinuteLimiter:
    """로그인 사용자 채팅 1분 10회(3-7-3, CHAT_RATE_LIMIT_PER_MINUTE). 사용자 ID별 최근 60초를 센다."""

    def __init__(
        self,
        limit: int = MEMBER_PER_MINUTE_LIMIT,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    # 한도 안이면 기록하고 True, 넘으면 기록하지 않고 False. 확인과 기록을 한 번에 한다.
    def take(self, user_id: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[user_id]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True


def member_limiter_from_env() -> MemberMinuteLimiter:
    try:
        limit = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", MEMBER_PER_MINUTE_LIMIT))
    except ValueError:
        limit = MEMBER_PER_MINUTE_LIMIT
    return MemberMinuteLimiter(max(limit, 1))
