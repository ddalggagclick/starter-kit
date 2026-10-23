# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 앱 로그 안전 출력 시험.
# PRD: 7-4-3.
# 구현할 기능: 허용 6개 필드만 출력되고 원문·토큰·비밀값·예외 내용이 빠지는지 확인.
# 완료 기준: 외부 서비스 없이 통과.
"""core/safe_logging.py 시험. 외부 서비스를 호출하지 않는다."""

from __future__ import annotations

import json
import logging
import sys

import pytest
from inheritance.core.safe_logging import (
    ALLOWED_LOG_FIELDS,
    FILTERED,
    SAFE_LOG_HANDLER_NAME,
    SafeLogFormatter,
    install_safe_logging,
)
from inheritance.main import create_app

QUESTION = "어머니가 남긴 빚이 3천만원인데 상속포기 해야 하나요"
SECRETS = ("handoff-token-abc123", "refresh-xyz789", "pw-1234!", "kakao-user-42", "AIzaFakeKey")


def record(msg="%s", args=(QUESTION,), name="inheritance.chat", exc_info=None, **extra):
    item = logging.LogRecord(name, logging.ERROR, __file__, 1, msg, args, exc_info)
    for key, value in extra.items():
        setattr(item, key, value)
    return item


def formatted(item: logging.LogRecord) -> tuple[str, dict]:
    line = SafeLogFormatter().format(item)
    return line, json.loads(line)


def test_only_allowed_fields_are_written():
    line, data = formatted(
        record(
            event="chat.answer",
            status="answered",
            error_code="PROVIDER_TIMEOUT",
            duration_ms=1234.56,
            trace_id="req-1",
            question=QUESTION,
            user_id=SECRETS[3],
            token=SECRETS[0],
        )
    )
    assert set(data) == set(ALLOWED_LOG_FIELDS)
    assert data["event"] == "chat.answer"
    assert data["status"] == "answered"
    assert data["error_code"] == "PROVIDER_TIMEOUT"
    assert data["duration_ms"] == 1234.6
    assert data["trace_id"] == "req-1"
    assert QUESTION not in line
    assert all(secret not in line for secret in SECRETS)


def test_message_and_args_are_never_written():
    line, data = formatted(
        record("질문=%s 토큰=%s 비밀번호=%s", (QUESTION, SECRETS[0], SECRETS[2]))
    )
    assert QUESTION not in line and SECRETS[0] not in line and SECRETS[2] not in line
    # event를 주지 않으면 로거 이름만 남는다.
    assert data == {"timestamp": data["timestamp"], "event": "inheritance.chat"}


@pytest.mark.parametrize("field", ["event", "status", "error_code", "trace_id"])
def test_sentence_values_in_allowed_fields_are_filtered(field):
    line, data = formatted(record(**{field: QUESTION}))
    assert data[field] == FILTERED
    assert QUESTION not in line


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "12", None])
def test_bad_duration_is_dropped(value):
    _, data = formatted(record(duration_ms=value))
    assert "duration_ms" not in data


def test_exception_keeps_only_its_type_name():
    try:
        raise ValueError(QUESTION)
    except ValueError:
        line, data = formatted(record(exc_info=sys.exc_info()))
    assert data["error_code"] == "ValueError"
    assert QUESTION not in line and "Traceback" not in line


def test_uvicorn_access_log_keeps_status_but_not_path():
    args = ("127.0.0.1:5000", "POST", f"/api/handoff/exchange?token={SECRETS[0]}", "1.1", 400)
    line, data = formatted(record('%s - "%s %s HTTP/%s" %d', args, name="uvicorn.access"))
    assert data["event"] == "uvicorn.access" and data["status"] == 400
    assert SECRETS[0] not in line and "127.0.0.1" not in line


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    saved_root = (root.level, list(root.handlers))
    saved = {
        name: (logging.getLogger(name).propagate, list(logging.getLogger(name).handlers))
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    yield
    root.setLevel(saved_root[0])
    root.handlers[:] = saved_root[1]
    for name, (propagate, handlers) in saved.items():
        logging.getLogger(name).propagate = propagate
        logging.getLogger(name).handlers[:] = handlers


@pytest.mark.usefixtures("restore_logging")
def test_create_app_installs_one_safe_handler_and_routes_uvicorn_logs():
    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.StreamHandler())
    access.propagate = False
    create_app()
    install_safe_logging()
    safe = [h for h in logging.getLogger().handlers if h.get_name() == SAFE_LOG_HANDLER_NAME]
    assert len(safe) == 1 and isinstance(safe[0].formatter, SafeLogFormatter)
    assert access.handlers == [] and access.propagate is True
