# 담당: [통합] 영역, 구현 B1 김현주(통합 허용) | 책임: 앱 로그를 허용된 6개 필드만 출력한다.
# PRD: E7 / 태스크 7-4-3.
# 구현할 기능: 메시지 본문·인자·예외 내용·그 밖의 필드를 버리고 JSON 한 줄로 출력한다.
# 완료 기준: 질문·답변 원문, 토큰, 비밀번호, 계정 식별값, API 키가 어떤 로그에도 나오지 않는다.
# 제한사항: 같은 프로세스(backend 서버)의 로그만 다룬다. 서버 밖 CLI 로그는 각 영역에서 확인한다.
"""허용 필드: timestamp, event, status, error_code, duration_ms, trace_id (PRD 7-4-3).

값은 `logger.info("...", extra={"event": "...", "status": 200})`처럼 extra로 넘긴다.
메시지 문자열은 출력하지 않으므로 원문을 넣어도 남지 않는다.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime

ALLOWED_LOG_FIELDS = ("timestamp", "event", "status", "error_code", "duration_ms", "trace_id")
FILTERED = "[filtered]"
SAFE_LOG_HANDLER_NAME = "inheritance-safe-log"

# 식별자 모양(영문·숫자·_.:-, 64자 이하)만 그대로 둔다. 문장·원문이 들어오면 [filtered]로 바꾼다.
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# uvicorn access 로그 인자: (client, method, path, http_version, status_code). 경로는 버린다.
_ACCESS_STATUS_INDEX = 4


class SafeLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        status = getattr(record, "status", None)
        if status is None and record.name == "uvicorn.access":
            status = _access_status(record.args)
        error_code = getattr(record, "error_code", None)
        if error_code is None and record.exc_info and record.exc_info[0] is not None:
            # 예외 메시지·traceback에는 원문이 섞일 수 있어 예외 종류 이름만 남긴다.
            error_code = record.exc_info[0].__name__
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "event": _safe_token(getattr(record, "event", None) or record.name),
            "status": _safe_status(status),
            "error_code": _safe_token(error_code),
            "duration_ms": _safe_duration(getattr(record, "duration_ms", None)),
            "trace_id": _safe_token(getattr(record, "trace_id", None)),
        }
        return json.dumps({k: v for k, v in entry.items() if v is not None}, ensure_ascii=False)


# 앱 시작 시 한 번 부른다. 루트 로거에 안전 출력 하나를 달고 uvicorn 로그도 그쪽으로 모은다.
def install_safe_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not any(handler.get_name() == SAFE_LOG_HANDLER_NAME for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.set_name(SAFE_LOG_HANDLER_NAME)
        handler.setFormatter(SafeLogFormatter())
        root.addHandler(handler)
    root.setLevel(level)
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def _safe_token(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    return FILTERED


def _safe_status(value: object) -> int | str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return _safe_token(value)


def _safe_duration(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return round(float(value), 1)


def _access_status(args: object) -> int | None:
    if isinstance(args, tuple) and len(args) > _ACCESS_STATUS_INDEX:
        status = args[_ACCESS_STATUS_INDEX]
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None
