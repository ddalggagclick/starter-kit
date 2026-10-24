# 담당: [통합] | 책임: rag.chunks 초기 migration의 오프라인 생성·범위 검사.
# PRD: E7 / 스토리 7-3 / 태스크 7-3-3
# 구현할 기능: 승인되지 않은 테이블과 확장 자동 설치가 없는지 확인한다.
# 완료 기준: Alembic SQL은 운영 DB 접속 없이 생성된다.
# 제한사항: 테스트에서 migration 실행·자료 적재를 하지 않는다.
"""Alembic 오프라인 SQL 계약 시험."""

from __future__ import annotations

import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
URL = "postgresql+asyncpg://postgres.demo:secret@fake.pooler.supabase.com:5432/postgres"


def test_승인된_RAG_도메인_테이블만_생성한다():
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    output = StringIO()
    with (
        patch.dict(os.environ, {"DATABASE_URL": URL, "APP_ENV": "test"}, clear=True),
        redirect_stdout(output),
    ):
        command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE SCHEMA IF NOT EXISTS rag" in sql
    assert "CREATE TABLE rag.chunks" in sql
    assert "content TEXT NOT NULL" in sql
    assert "embedding extensions.vector(768) NOT NULL" in sql
    assert "extensions.vector(768)" in sql
    assert "extensions.vector_cosine_ops" in sql
    assert "chunks_embedding_hnsw_idx" in sql
    assert "chunks_publication_scope_idx" in sql
    assert "chunks_publication_state_check" in sql
    assert "CREATE EXTENSION" not in sql.upper()
    assert "rag.documents" not in sql and "rag.evidence" not in sql
    assert "DROP TABLE" not in sql.upper()
    assert "secret" not in sql
    columns = sql.split("CREATE TABLE rag.chunks (", 1)[1].split(");", 1)[0]
    assert columns.count("\n    ") >= 16


def test_DATABASE_URL_누락을_거부한다():
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    with patch.dict(os.environ, {}, clear=True):
        try:
            command.upgrade(config, "head", sql=True)
        except ValueError as exc:
            assert str(exc) == "DATABASE_URL is required for explicit Alembic commands"
        else:
            raise AssertionError("Alembic must not run without explicit database configuration")


def test_예상하지_못한_URL_파싱_오류를_숨기지_않는다():
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    with (
        patch.dict(os.environ, {"DATABASE_URL": URL, "APP_ENV": "test"}, clear=True),
        patch(
            "sqlalchemy.engine.make_url",
            side_effect=RuntimeError("unexpected URL parser failure"),
        ),
        redirect_stdout(StringIO()),
    ):
        try:
            command.upgrade(config, "head", sql=True)
        except RuntimeError as exc:
            assert str(exc) == "unexpected URL parser failure"
        else:
            raise AssertionError("unexpected URL parser failures must not be hidden")
