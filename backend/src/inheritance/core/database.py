# 담당: [통합] | 책임: 비동기 DB 엔진과 요청별 세션 수명.
# PRD: E7 / 스토리 7-3 / 태스크 7-3-3 (앱 조립 지원: 7-1-4)
# 구현할 기능: 세션 제공, 오류 시 rollback, 앱 종료 시 엔진 정리를 수행한다.
# 완료 기준: 세션과 연결 풀이 요청·앱 수명에 맞게 반환된다.
# 제한사항: DB 변경은 승인된 스키마만 사용한다. commit은 업무 서비스가 소유한다.
"""실제 사용자/토큰 테이블은 ERD 승인 및 Alembic 작업 후 구현한다."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings

logger = logging.getLogger(__name__)


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Server-side Supavisor Session Pooler + conservative app connection pool."""
    # Supabase 연결은 로컬 APP_ENV에서도 TLS를 강제한다.
    hostname = urlsplit(settings.database_url).hostname or ""
    require_tls = settings.production or hostname.endswith(".pooler.supabase.com")
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={"ssl": "require"} if require_tls else {},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def db_session(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """FastAPI Depends에서 사용; transaction commit은 service에서 1회, 실패는 rollback."""
    async with factory() as session:
        try:
            yield session
        except BaseException:
            # BaseException에 포함되는 요청 취소에서도 열린 트랜잭션을 되돌린다.
            await session.rollback()
            raise


async def dispose_db_engine(engine: AsyncEngine) -> None:
    """FastAPI lifespan shutdown에서 호출."""
    await engine.dispose()


def create_sync_db_engine(settings: Settings) -> Engine:
    """인증·A17 저장소용 동기 엔진(psycopg). 인증 라우터가 동기 함수라 스레드에서 쓴다."""
    url = make_url(settings.database_url).set(drivername="postgresql+psycopg")
    hostname = url.host or ""
    require_tls = settings.production or hostname.endswith(".pooler.supabase.com")
    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"} if require_tls else {},
    )


class DatabaseConfigurationError(RuntimeError):
    """DATABASE_URL이 있는데 잘못됨. 메모리 저장소로 넘어가지 않고 서버 시작을 멈춘다(PR #142 리뷰)."""


def sync_db_engine_from_env() -> Engine | None:
    """DATABASE_URL이 비어 있으면 None(메모리 저장소). 있는데 잘못되면 시작 실패.

    조용히 메모리로 넘어가면 재시작 때 계정이 사라지는데도 알아채기 어렵다. 오류 문구에 접속 정보는 넣지 않는다.
    """
    if not os.environ.get("DATABASE_URL", "").strip():
        return None
    try:
        return create_sync_db_engine(Settings.from_env())
    except (ValueError, ArgumentError):
        logger.error("app.db", extra={"event": "app.db", "status": "invalid_settings"})
        raise DatabaseConfigurationError(
            "DATABASE_URL 설정이 올바르지 않습니다(Supabase Session Pooler 5432 확인)"
        ) from None
