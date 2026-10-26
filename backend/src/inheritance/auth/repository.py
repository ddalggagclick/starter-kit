# 담당: [통합] | 책임: 사용자와 RefreshSession의 영속 접근.
# PRD: E5 / 스토리 5-2, 5-3 / 태스크 5-2-3, 5-3-2
# 구현할 기능: 세션 회전과 재사용 탐지에 필요한 조회·상태 갱신을 제공한다.
# 완료 기준: 세션 변경이 승인된 트랜잭션 경계 안에서 처리된다.
# 제한사항: ERD 승인 전 저장 구조를 추가하지 않는다. 채팅 본문을 저장하지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""인증 저장소. ERD 승인 전이라 프로세스 메모리에 둔다(재시작하면 사라진다).

DB 저장소는 ERD 승인 후 같은 메서드로 만든다. 모든 변경은 잠금 안에서 한 번에 처리한다.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Literal, Protocol

from inheritance.auth.models import OneTimeKind, OneTimeToken, RefreshSession, User

ConsumeState = Literal["ok", "invalid", "reused"]


# 메모리 저장소와 DB 저장소(db_repository.PostgresAuthRepository)가 같은 메서드를 가진다.
class AuthRepository(Protocol):
    def add_user(self, user: User) -> bool: ...
    def user_by_email(self, email: str) -> User | None: ...
    def user_by_id(self, user_id: str) -> User | None: ...
    def update_user(self, user: User) -> None: ...
    def delete_user(self, user_id: str) -> int: ...
    def add_session(self, session: RefreshSession) -> None: ...
    def consume_session(
        self, token_hash: str, now: float
    ) -> tuple[ConsumeState, RefreshSession | None]: ...
    def revoke_session(self, token_hash: str) -> None: ...
    def revoke_user_sessions(self, user_id: str) -> int: ...
    def add_token(self, token: OneTimeToken) -> None: ...
    def consume_token(
        self, token_hash: str, kind: OneTimeKind, now: float
    ) -> OneTimeToken | None: ...


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}
        self._emails: dict[str, str] = {}
        self._sessions: dict[str, RefreshSession] = {}
        self._tokens: dict[str, OneTimeToken] = {}

    def add_user(self, user: User) -> bool:
        with self._lock:
            if user.email in self._emails:
                return False
            self._users[user.user_id] = user
            self._emails[user.email] = user.user_id
            return True

    def user_by_email(self, email: str) -> User | None:
        with self._lock:
            user = self._users.get(self._emails.get(email, ""))
            return replace(user) if user else None

    def user_by_id(self, user_id: str) -> User | None:
        with self._lock:
            user = self._users.get(user_id)
            return replace(user) if user else None

    def update_user(self, user: User) -> None:
        with self._lock:
            if user.user_id in self._users:
                self._users[user.user_id] = replace(user)

    def delete_user(self, user_id: str) -> int:
        with self._lock:
            user = self._users.pop(user_id, None)
            if user is not None:
                self._emails.pop(user.email, None)
            self._tokens = {k: t for k, t in self._tokens.items() if t.user_id != user_id}
            return self._drop_sessions(lambda s: s.user_id == user_id)

    def add_session(self, session: RefreshSession) -> None:
        with self._lock:
            self._sessions[session.token_hash] = replace(session)

    # 회전의 핵심: 조회와 '사용됨' 표시를 한 번에 한다. 이미 사용된 세션이면 그 가족 전체를 끊는다.
    def consume_session(self, token_hash: str, now: float) -> tuple[str, RefreshSession | None]:
        with self._lock:
            session = self._sessions.get(token_hash)
            if session is None or session.revoked or session.expires_at <= now:
                return "invalid", None
            if session.used:
                for item in self._sessions.values():
                    if item.family_id == session.family_id:
                        item.revoked = True
                return "reused", None
            session.used = True
            return "ok", replace(session)

    def revoke_session(self, token_hash: str) -> None:
        with self._lock:
            session = self._sessions.get(token_hash)
            if session is not None:
                session.revoked = True

    def revoke_user_sessions(self, user_id: str) -> int:
        with self._lock:
            return self._drop_sessions(lambda s: s.user_id == user_id)

    def add_token(self, token: OneTimeToken) -> None:
        with self._lock:
            self._tokens[token.token_hash] = replace(token)

    # 1회용 링크: 조회와 사용 처리를 한 번에 한다. 만료·사용·없음은 같은 결과(None)다.
    def consume_token(self, token_hash: str, kind: OneTimeKind, now: float) -> OneTimeToken | None:
        with self._lock:
            token = self._tokens.get(token_hash)
            if token is None or token.kind != kind or token.used or token.expires_at <= now:
                return None
            token.used = True
            return replace(token)

    def _drop_sessions(self, match) -> int:
        dropped = [k for k, s in self._sessions.items() if match(s)]
        for key in dropped:
            del self._sessions[key]
        return len(dropped)
