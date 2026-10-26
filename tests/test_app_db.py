# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 계정·A17 Supabase DB 저장소 시험.
# PRD: 5-1-3, 4-6-2, 5-4-2, 4-5-2.
# 구현할 기능: Alembic SQL, 엔진 설정, DB 저장소 동작(회전·재사용 탐지·1회용 링크·CASCADE)을 확인.
# 완료 기준: DB 없이 도는 시험은 항상 통과. 실제 DB 시험은 APP_DB_INTEGRATION=1과 DATABASE_URL이 있을 때만.
"""실제 DB 시험은 고유 ID로 만들고 끝나면 지운다. 운영 DB에 실수로 쓰지 않게 명시적으로 켜야 돈다."""

from __future__ import annotations

import io
import os
import time
import uuid
from contextlib import redirect_stdout

import pytest
from alembic import command
from alembic.config import Config
from inheritance.auth.db_repository import PostgresAuthRepository
from inheritance.auth.models import OneTimeToken, RefreshSession, User
from inheritance.checklist.server_storage import PostgresServerChecklistStore
from inheritance.core.database import sync_db_engine_from_env

POOLER = (
    "postgresql+asyncpg://postgres.abcdefghijklmnopqrst:secret-pw"
    "@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
)


def test_alembic_app_revision_sql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", POOLER)
    cfg = Config()
    cfg.set_main_option("script_location", "backend/migrations")
    out = io.StringIO()
    cfg.stdout = out
    with redirect_stdout(out):
        command.upgrade(cfg, "20261023_01_rag_chunks:20261026_01_app_accounts", sql=True)
    sql = out.getvalue()
    for table in ("users", "refresh_sessions", "one_time_tokens", "server_checklists"):
        assert f"CREATE TABLE app.{table}" in sql
    assert sql.count("ON DELETE CASCADE") == 3
    assert "UNIQUE (email)" in sql
    # 원문 비밀번호·토큰·AI 질문 답변 컬럼이 없다(해시만 저장, 4-5-2).
    for banned in (" password TEXT", " token TEXT", "question", "answer"):
        assert banned not in sql
    assert "secret-pw" not in sql


def test_engine_none_without_or_with_invalid_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert sync_db_engine_from_env() is None
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@127.0.0.1:5432/postgres")
    assert sync_db_engine_from_env() is None


def test_engine_uses_psycopg_and_tls_for_pooler(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", POOLER)
    engine = sync_db_engine_from_env()
    assert engine is not None
    assert engine.url.drivername == "postgresql+psycopg"
    assert "secret-pw" not in repr(engine)
    engine.dispose()


# ---- 실제 DB (명시적으로 켤 때만) -------------------------------------------------------

integration = pytest.mark.skipif(
    os.environ.get("APP_DB_INTEGRATION") != "1" or not os.environ.get("DATABASE_URL"),
    reason="실제 DB 시험은 APP_DB_INTEGRATION=1과 DATABASE_URL이 있을 때만 돈다",
)


@pytest.fixture
def engine():
    engine = sync_db_engine_from_env()
    assert engine is not None, "DATABASE_URL 설정 확인 필요"
    yield engine
    engine.dispose()


@pytest.fixture
def user(engine):
    repo = PostgresAuthRepository(engine)
    item = User(f"test-{uuid.uuid4().hex}", f"t{uuid.uuid4().hex[:12]}@example.com", "hash")
    assert repo.add_user(item)
    yield item
    repo.delete_user(item.user_id)


@integration
def test_db_users_and_unique_email(engine, user):
    repo = PostgresAuthRepository(engine)
    assert repo.add_user(User(f"test-{uuid.uuid4().hex}", user.email, "h")) is False
    found = repo.user_by_email(user.email)
    assert found is not None and found.user_id == user.user_id and not found.verified
    found.verified = True
    repo.update_user(found)
    assert repo.user_by_id(user.user_id).verified is True


@integration
def test_db_refresh_rotation_and_reuse_detection(engine, user):
    repo = PostgresAuthRepository(engine)
    now = time.time()
    family = uuid.uuid4().hex
    repo.add_session(RefreshSession("h1-" + family, user.user_id, family, now + 600))
    repo.add_session(RefreshSession("h2-" + family, user.user_id, family, now + 600))
    state, session = repo.consume_session("h1-" + family, now)
    assert state == "ok" and session.user_id == user.user_id
    # 같은 토큰을 다시 쓰면 재사용 탐지 → 같은 계열 전체 무효
    assert repo.consume_session("h1-" + family, now)[0] == "reused"
    assert repo.consume_session("h2-" + family, now)[0] == "invalid"
    assert repo.consume_session("missing", now)[0] == "invalid"


@integration
def test_db_one_time_token_consumed_once_and_expires(engine, user):
    repo = PostgresAuthRepository(engine)
    now = time.time()
    tag = uuid.uuid4().hex
    repo.add_token(OneTimeToken("v-" + tag, "email_verify", user.user_id, now + 600))
    repo.add_token(OneTimeToken("old-" + tag, "email_verify", user.user_id, now - 1))
    assert repo.consume_token("v-" + tag, "password_reset", now) is None
    assert repo.consume_token("v-" + tag, "email_verify", now).user_id == user.user_id
    assert repo.consume_token("v-" + tag, "email_verify", now) is None
    assert repo.consume_token("old-" + tag, "email_verify", now) is None


@integration
def test_db_checklist_overwrite_and_cascade_delete(engine, user):
    store = PostgresServerChecklistStore(engine)
    repo = PostgresAuthRepository(engine)
    assert store.get(user.user_id) is None
    store.put(user.user_id, ({"kind": "inheritance-checklist", "version": 1, "a": "가"},))
    store.put(user.user_id, ({"kind": "inheritance-checklist", "version": 1, "a": "나"},))
    assert store.get(user.user_id).item_states == (
        {"kind": "inheritance-checklist", "version": 1, "a": "나"},
    )
    repo.add_session(RefreshSession("s-" + user.user_id, user.user_id, "f", time.time() + 60))
    assert repo.delete_user(user.user_id) == 1
    # 사용자 삭제 → 세션·체크리스트 CASCADE
    assert store.get(user.user_id) is None
    assert repo.consume_session("s-" + user.user_id, time.time())[0] == "invalid"


def test_app_uses_db_repositories_only_with_database_url(monkeypatch):
    from inheritance.auth.repository import InMemoryAuthRepository
    from inheritance.main import create_app

    monkeypatch.setenv("JWT_SIGNING_KEY", "j" * 32)
    monkeypatch.setenv("CSRF_SECRET", "c" * 32)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    memory_app = create_app()
    assert memory_app.state.db_engine is None
    assert isinstance(memory_app.state.auth_service._repo, InMemoryAuthRepository)

    monkeypatch.setenv("DATABASE_URL", POOLER)
    db_app = create_app()  # 엔진은 접속을 미루므로 여기서 DB에 연결하지 않는다.
    assert isinstance(db_app.state.auth_service._repo, PostgresAuthRepository)
    db_app.state.db_engine.dispose()
