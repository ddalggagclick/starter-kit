# 담당: [통합] | 책임: 승인된 RAG 초기 revision의 명시적 실행 환경.
# PRD: E7 / 스토리 7-3 / 태스크 7-3-3
# 구현할 기능: DATABASE_URL을 Alembic 온라인·오프라인 환경에 연결한다.
# 완료 기준: 실제 앱 시작과 분리하고, 오프라인 SQL을 생성할 수 있다.
# 제한사항: 운영 DB에 자동 적용하거나 pgvector를 설치하지 않는다.
"""명시적으로 실행한 Alembic 명령에만 DB 연결을 제공한다."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine as sqlalchemy_engine, pool
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name and config.get_section(config.config_ini_section).get("loggers"):
    fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise ValueError("DATABASE_URL is required for explicit Alembic commands")
    try:
        url = sqlalchemy_engine.make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL is not a valid PostgreSQL connection URL") from None
    if url.drivername != "postgresql+asyncpg" or url.port != 5432 or not url.host:
        raise ValueError("Alembic DATABASE_URL must use postgresql+asyncpg on port 5432")
    if not url.host.endswith(".pooler.supabase.com"):
        raise ValueError("Alembic requires the approved Supabase Session Pooler")
    return value


def run_migrations_offline() -> None:
    # --sql 옵션은 접속 없이 SQL만 생성한다. 출력에 비밀번호를 포함하지 않는다.
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_async() -> None:
    url = sqlalchemy_engine.make_url(_database_url())
    engine = async_engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"ssl": "require"},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_migrations_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
