"""Error categories give next steps without echoing sensitive exception text."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError
from starter_rag.diagnostics import diagnose
from starter_rag.ingestion.review import ReviewError
from starter_rag.storage.database import DatabaseSchemaError


def test_데이터베이스_초기화와_연결_실패를_구분한다() -> None:
    assert "DB 미초기화" in diagnose(DatabaseSchemaError("secret-password"), "search")
    error = OperationalError("SELECT secret-password", {}, RuntimeError("token=hidden"))
    message = diagnose(error, "index")
    assert "DB 연결 실패" in message
    assert "secret-password" not in message
    assert "token=hidden" not in message


def test_검토와_컨텍스트_진단에서_비밀값을_출력하지_않는다() -> None:
    assert "HITL 승인 오류" in diagnose(ReviewError("secret-token"), "publish")
    result = diagnose(RuntimeError("context length exceeded, token=secret-token"), "chunk")
    assert "LLM 컨텍스트 초과" in result
    assert "secret-token" not in result
