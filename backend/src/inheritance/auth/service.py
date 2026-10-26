# 담당: [통합] | 책임: 인증 토큰과 Refresh 세션의 수명주기.
# PRD: E5 / 스토리 5-2, 5-3 / 태스크 5-2-2, 5-2-3, 5-3-2
# 구현할 기능: 승인된 Access JWT 발급, Refresh 회전, 재사용 탐지와 세션 무효화를 수행한다.
# 완료 기준: 정상 사용과 만료·재사용·저장 실패를 구분해 처리한다.
# 제한사항: 이메일 공급자, 비밀번호 정책, 미확정 TTL은 임의로 정하지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""A11~A16 인증 규칙. HTTP와 쿠키는 router가, 저장은 repository가 맡는다.

openapi에 정해진 값: Access 15분, Refresh 7일·회전, 인증 링크 24시간·1회, 재설정 링크 30분·1회,
재전송 60초 간격·하루 5회, 로그인 실패 15분 안 5번이면 제한. 토큰 원문은 저장하지 않고 해시만 둔다.
이메일 공급자는 미정이라 EmailSender Port만 두고 기본값은 보내지 않는다.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from inheritance.auth.jwt import AccessTokenCodec
from inheritance.auth.models import OneTimeKind, OneTimeToken, RefreshSession, User
from inheritance.auth.password import hash_password, password_policy_ok, verify_password
from inheritance.auth.repository import InMemoryAuthRepository

VERIFY_TTL_SECONDS = 24 * 60 * 60
RESET_TTL_SECONDS = 30 * 60
RESEND_INTERVAL_SECONDS = 60
RESEND_DAILY_LIMIT = 5
DAY_SECONDS = 24 * 60 * 60


class AuthError(Exception):
    """router가 ErrorCode로 바꾸는 이유 값. 사용자 입력이나 토큰은 담지 않는다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# 메일 발송 방식은 미정이다. 실제 발송기는 결정 후 이 Port로 끼운다. 토큰을 로그에 남기지 않는다.
class EmailSender(Protocol):
    def send_verification(self, email: str, token: str) -> None: ...

    def send_password_reset(self, email: str, token: str) -> None: ...


class NoEmailSender:
    """발송 방식 결정 전 기본값. 아무것도 보내지 않는다(그래서 실서버에서는 인증을 끝낼 수 없다)."""

    def send_verification(self, email: str, token: str) -> None:
        return None

    def send_password_reset(self, email: str, token: str) -> None:
        return None


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


class _SlidingWindow:
    """이메일별 최근 시각 기록. 인증 경로는 여러 스레드에서 동시에 돌아서 잠금 안에서만 바꾼다."""

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._lock = threading.Lock()
        self._items: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str, now: float) -> deque[float]:
        items = self._items[key]
        while items and now - items[0] >= self._window:
            items.popleft()
        return items

    def count(self, key: str, now: float) -> int:
        with self._lock:
            return len(self._recent(key, now))

    def add(self, key: str, now: float) -> None:
        with self._lock:
            self._recent(key, now).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    # 간격·횟수 안이면 기록하고 True. 확인과 기록을 한 번에 해서 동시 요청이 함께 통과하지 못한다.
    def take(self, key: str, now: float, limit: int, min_interval: float) -> bool:
        with self._lock:
            recent = self._recent(key, now)
            if (recent and now - recent[-1] < min_interval) or len(recent) >= limit:
                return False
            recent.append(now)
            return True


class AuthService:
    def __init__(
        self,
        repository: InMemoryAuthRepository,
        access: AccessTokenCodec,
        email: EmailSender | None = None,
        refresh_ttl_seconds: int = 7 * 24 * 60 * 60,
        login_failure_limit: int = 5,
        login_failure_window_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._repo = repository
        self._access = access
        self._email = email or NoEmailSender()
        self._refresh_ttl = refresh_ttl_seconds
        self._failure_limit = login_failure_limit
        self._clock = clock
        self._failures = _SlidingWindow(login_failure_window_seconds)
        self._resends = _SlidingWindow(DAY_SECONDS)
        self._reset_requests = _SlidingWindow(DAY_SECONDS)
        # 탈퇴 시 함께 지울 계정 자료(예: A17 서버 체크리스트). 저장 기능이 자기 삭제 함수를 등록한다.
        self._account_deleted: list[Callable[[str], None]] = []

    def on_account_deleted(self, hook: Callable[[str], None]) -> None:
        self._account_deleted.append(hook)

    @property
    def deletes_server_checklist(self) -> bool:
        return bool(self._account_deleted)

    # A11: 이메일 인증 전에는 로그인할 수 없다.
    def signup(self, email: str, password: str) -> None:
        if not password_policy_ok(password):
            raise AuthError("validation")
        user = User(uuid.uuid4().hex, normalize_email(email), hash_password(password))
        if not self._repo.add_user(user):
            raise AuthError("email_taken")
        self._send_one_time(user, "email_verify")

    # A12: 24시간·1회. 만료·사용·없음은 같은 오류다.
    def verify_email(self, token: str) -> None:
        item = self._repo.consume_token(_hash(token), "email_verify", self._clock())
        user = self._repo.user_by_id(item.user_id) if item else None
        if user is None:
            raise AuthError("token_invalid")
        user.verified = True
        self._repo.update_user(user)

    # A12 재전송: 가입 여부를 알리지 않는다. 간격·횟수 제한은 이메일 기준으로 항상 센다.
    def resend_verification(self, email: str) -> None:
        key = normalize_email(email)
        if not self._resends.take(key, self._clock(), RESEND_DAILY_LIMIT, RESEND_INTERVAL_SECONDS):
            raise AuthError("rate_limited")
        user = self._repo.user_by_email(key)
        if user is not None and not user.verified:
            self._send_one_time(user, "email_verify")

    # A13: 실패는 이메일 기준 15분 안 5번까지. 제한 중에는 비밀번호가 맞아도 막는다.
    def login(self, email: str, password: str) -> IssuedTokens:
        key = normalize_email(email)
        now = self._clock()
        if self._failures.count(key, now) >= self._failure_limit:
            raise AuthError("rate_limited")
        user = self._repo.user_by_email(key)
        if user is None or not verify_password(password, user.password_hash):
            self._failures.add(key, now)
            raise AuthError("unauthenticated")
        if not user.verified:
            raise AuthError("not_verified")
        self._failures.clear(key)
        return self._issue(user.user_id, uuid.uuid4().hex, now)

    # A14: 쓴 Refresh는 다시 쓸 수 없다. 이미 쓴 것이 또 오면 탈취로 보고 그 가족 전체를 끊는다.
    def refresh(self, refresh_token: str | None) -> IssuedTokens:
        if not refresh_token:
            raise AuthError("refresh_invalid")
        now = self._clock()
        state, session = self._repo.consume_session(_hash(refresh_token), now)
        if state != "ok" or session is None or self._repo.user_by_id(session.user_id) is None:
            raise AuthError("refresh_invalid")
        return self._issue(session.user_id, session.family_id, now)

    def logout(self, refresh_token: str | None) -> None:
        if refresh_token:
            self._repo.revoke_session(_hash(refresh_token))

    # A15: 가입 여부를 알리지 않고 항상 같은 결과다. 메일 폭탄을 막으려고 재전송과 같은 간격·횟수를
    # 넘으면 조용히 보내지 않는다(openapi 응답은 항상 202라 429를 새로 만들지 않는다).
    def request_password_reset(self, email: str) -> None:
        key = normalize_email(email)
        if not self._reset_requests.take(
            key, self._clock(), RESEND_DAILY_LIMIT, RESEND_INTERVAL_SECONDS
        ):
            return
        user = self._repo.user_by_email(key)
        if user is not None:
            self._send_one_time(user, "password_reset")

    # A15: 30분·1회. 바꾸면 모든 기기에서 로그아웃된다.
    def reset_password(self, token: str, new_password: str) -> None:
        if not password_policy_ok(new_password):
            raise AuthError("validation")
        item = self._repo.consume_token(_hash(token), "password_reset", self._clock())
        user = self._repo.user_by_id(item.user_id) if item else None
        if user is None:
            raise AuthError("token_invalid")
        user.password_hash = hash_password(new_password)
        self._repo.update_user(user)
        self._repo.revoke_user_sessions(user.user_id)

    def user_id_from_access(self, access_token: str) -> str:
        return self._access.verify(access_token)

    # A16: 비밀번호를 한 번 더 확인한다. 서버 체크리스트 저장(A17)은 아직 없어 지울 것이 없다.
    def delete_account(self, user_id: str, password: str) -> int:
        user = self._repo.user_by_id(user_id)
        if user is None:
            raise AuthError("unauthenticated")
        if not verify_password(password, user.password_hash):
            raise AuthError("forbidden")
        # 5-4-2: 서버에 남은 계정 자료를 먼저 지우고 계정을 지운다. 자료 삭제가 실패하면 계정은 남아
        # 다시 탈퇴할 수 있다(계정만 사라지고 자료가 남는 상태를 만들지 않는다).
        for hook in self._account_deleted:
            hook(user_id)
        return self._repo.delete_user(user_id)

    def _issue(self, user_id: str, family_id: str, now: float) -> IssuedTokens:
        refresh_token = secrets.token_urlsafe(32)
        self._repo.add_session(
            RefreshSession(_hash(refresh_token), user_id, family_id, now + self._refresh_ttl)
        )
        access_token = self._access.issue(user_id, int(now))
        return IssuedTokens(access_token, self._access.ttl_seconds, refresh_token)

    def _send_one_time(self, user: User, kind: OneTimeKind) -> None:
        token = secrets.token_urlsafe(32)
        ttl = VERIFY_TTL_SECONDS if kind == "email_verify" else RESET_TTL_SECONDS
        self._repo.add_token(OneTimeToken(_hash(token), kind, user.user_id, self._clock() + ttl))
        if kind == "email_verify":
            self._email.send_verification(user.email, token)
        else:
            self._email.send_password_reset(user.email, token)
