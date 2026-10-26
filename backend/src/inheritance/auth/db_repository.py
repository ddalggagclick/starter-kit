# 담당: [통합] 영역, 구현 B1 김현주(통합 허용) | 책임: 회원·Refresh 세션·1회용 링크의 PostgreSQL 저장소.
# PRD: E5 / 5-1-3, 5-3-2, 5-4-2.
# 구현할 기능: InMemoryAuthRepository와 같은 메서드를 app 스키마 테이블로 제공한다.
# 완료 기준: 비밀번호·토큰은 해시만 저장하고, Refresh 회전·링크 소비가 동시 요청에서도 한 번만 성공한다.
# 제한사항: 테이블은 Alembic revision 20261026_01_app_accounts로만 만든다. 값·쿼리 원문을 로그에 남기지 않는다.
"""인증 라우터는 동기 함수(스레드)로 돌아서 동기 SQLAlchemy 엔진(psycopg)을 쓴다."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, text

from inheritance.auth.models import OneTimeKind, OneTimeToken, RefreshSession, User
from inheritance.auth.repository import ConsumeState


def _ts(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def _user(row) -> User:
    return User(row.user_id, row.email, row.password_hash, row.verified)


class PostgresAuthRepository:
    def __init__(self, engine: Engine, schema: str = "app") -> None:
        self._engine = engine
        self._s = schema

    def add_user(self, user: User) -> bool:
        sql = text(
            f"INSERT INTO {self._s}.users (user_id, email, password_hash, verified) "
            "VALUES (:id, :email, :hash, :verified) ON CONFLICT (email) DO NOTHING "
            "RETURNING user_id"
        )
        with self._engine.begin() as conn:
            row = conn.execute(
                sql,
                {
                    "id": user.user_id,
                    "email": user.email,
                    "hash": user.password_hash,
                    "verified": user.verified,
                },
            ).first()
        return row is not None

    def user_by_email(self, email: str) -> User | None:
        return self._one_user("email = :v", email)

    def user_by_id(self, user_id: str) -> User | None:
        return self._one_user("user_id = :v", user_id)

    def _one_user(self, where: str, value: str) -> User | None:
        sql = text(
            f"SELECT user_id, email, password_hash, verified FROM {self._s}.users WHERE {where}"
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"v": value}).first()
        return _user(row) if row else None

    def update_user(self, user: User) -> None:
        sql = text(
            f"UPDATE {self._s}.users SET password_hash = :hash, verified = :verified "
            "WHERE user_id = :id"
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql, {"id": user.user_id, "hash": user.password_hash, "verified": user.verified}
            )

    # 사용자를 지우면 세션·링크·서버 체크리스트는 FK CASCADE로 함께 지워진다. 지운 세션 수를 돌려준다.
    def delete_user(self, user_id: str) -> int:
        with self._engine.begin() as conn:
            sessions = conn.execute(
                text(f"SELECT count(*) FROM {self._s}.refresh_sessions WHERE user_id = :id"),
                {"id": user_id},
            ).scalar_one()
            conn.execute(text(f"DELETE FROM {self._s}.users WHERE user_id = :id"), {"id": user_id})
        return int(sessions)

    def add_session(self, session: RefreshSession) -> None:
        sql = text(
            f"INSERT INTO {self._s}.refresh_sessions "
            "(token_hash, user_id, family_id, expires_at, used, revoked) "
            "VALUES (:hash, :user, :family, :exp, :used, :revoked)"
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "hash": session.token_hash,
                    "user": session.user_id,
                    "family": session.family_id,
                    "exp": _ts(session.expires_at),
                    "used": session.used,
                    "revoked": session.revoked,
                },
            )

    # 행을 잠그고(FOR UPDATE) 확인과 '사용됨' 표시를 한 트랜잭션에서 한다. 이미 쓴 토큰이면 그 계열 전체를 끊는다.
    def consume_session(
        self, token_hash: str, now: float
    ) -> tuple[ConsumeState, RefreshSession | None]:
        select = text(
            f"SELECT user_id, family_id, expires_at, used, revoked "
            f"FROM {self._s}.refresh_sessions WHERE token_hash = :hash FOR UPDATE"
        )
        with self._engine.begin() as conn:
            row = conn.execute(select, {"hash": token_hash}).first()
            if row is None or row.revoked or row.expires_at <= _ts(now):
                return "invalid", None
            if row.used:
                conn.execute(
                    text(
                        f"UPDATE {self._s}.refresh_sessions SET revoked = true "
                        "WHERE family_id = :family"
                    ),
                    {"family": row.family_id},
                )
                return "reused", None
            conn.execute(
                text(f"UPDATE {self._s}.refresh_sessions SET used = true WHERE token_hash = :hash"),
                {"hash": token_hash},
            )
        session = RefreshSession(
            token_hash, row.user_id, row.family_id, row.expires_at.timestamp(), used=True
        )
        return "ok", session

    def revoke_session(self, token_hash: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {self._s}.refresh_sessions SET revoked = true WHERE token_hash = :hash"
                ),
                {"hash": token_hash},
            )

    def revoke_user_sessions(self, user_id: str) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(f"DELETE FROM {self._s}.refresh_sessions WHERE user_id = :id"), {"id": user_id}
            )
        return int(result.rowcount or 0)

    def add_token(self, token: OneTimeToken) -> None:
        sql = text(
            f"INSERT INTO {self._s}.one_time_tokens (token_hash, kind, user_id, expires_at, used) "
            "VALUES (:hash, :kind, :user, :exp, :used)"
        )
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "hash": token.token_hash,
                    "kind": token.kind,
                    "user": token.user_id,
                    "exp": _ts(token.expires_at),
                    "used": token.used,
                },
            )

    # 조건(종류·미사용·만료 전)을 만족할 때만 한 번의 UPDATE로 사용 처리한다. 만료·사용·없음은 같은 결과.
    def consume_token(self, token_hash: str, kind: OneTimeKind, now: float) -> OneTimeToken | None:
        sql = text(
            f"UPDATE {self._s}.one_time_tokens SET used = true "
            "WHERE token_hash = :hash AND kind = :kind AND used = false AND expires_at > :now "
            "RETURNING user_id, expires_at"
        )
        with self._engine.begin() as conn:
            row = conn.execute(sql, {"hash": token_hash, "kind": kind, "now": _ts(now)}).first()
        if row is None:
            return None
        return OneTimeToken(token_hash, kind, row.user_id, row.expires_at.timestamp(), used=True)
