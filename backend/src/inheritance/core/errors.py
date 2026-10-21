"""공통 오류 종류와 HTTP 변환 계약 (검토본).

담당: 통합 관리자. 책임: 예측 가능한 내부 오류를 코드·HTTP 상태에 매핑.
구현할 기능: 오류 분류, 요청 ID, 공개 가능한 메시지 키, 재시도 가능 여부.
경계: S7은 정상 HTTP 200의 판단 유보 결과이며 기술 오류가 아니다.
완료 기준: 각 코드의 HTTP 상태와 예상 공개 행동에 대한 계약 테스트.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    REFRESH_INVALID = "REFRESH_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    HANDOFF_INVALID = "HANDOFF_INVALID"
    CSRF_INVALID = "CSRF_INVALID"
    ORIGIN_FORBIDDEN = "ORIGIN_FORBIDDEN"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"  # frontend-local; not emitted as HTTP
    SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"  # S7 domain result HTTP 200
    CITATION_MISMATCH = "CITATION_MISMATCH"  # S7 domain result HTTP 200


HTTP_STATUS: dict[ErrorCode, int | None] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.REFRESH_INVALID: 401,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.HANDOFF_INVALID: 400,  # invalid/used/expired => one indistinguishable result
    ErrorCode.CSRF_INVALID: 403,
    ErrorCode.ORIGIN_FORBIDDEN: 403,
    ErrorCode.PROVIDER_RATE_LIMIT: 429,
    ErrorCode.PROVIDER_TIMEOUT: 504,
    ErrorCode.PROVIDER_UNAVAILABLE: 503,
    ErrorCode.STORAGE_UNAVAILABLE: None,
    ErrorCode.SOURCE_NOT_VERIFIED: 200,
    ErrorCode.CITATION_MISMATCH: 200,
}


@dataclass(frozen=True)
class AppError(Exception):
    code: ErrorCode
    request_id: str
    retryable: bool = False
    public_message_key: str = "generic_error"

    @property
    def http_status(self) -> int | None:
        return HTTP_STATUS[self.code]


def _known_code(value: object) -> ErrorCode | None:
    try:
        return ErrorCode(value)
    except ValueError:
        return None


# openapi Error 모양 {code, message}. 사용자 문구가 정해지기 전까지 message에는 코드 이름을 넣는다.
def error_body(code: ErrorCode, message: object = None) -> dict[str, str]:
    return {"code": code.value, "message": message if isinstance(message, str) else code.value}


# 오류 본문을 openapi Error 모양으로 맞춘다. 입력값·검증 상세는 본문과 로그에 넣지 않는다.
# 팀 오류 코드가 아닌 HTTPException(예: 404)은 FastAPI 기본 응답을 그대로 쓴다.
def install_error_handlers(app: FastAPI) -> None:
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and (code := _known_code(detail.get("code"))):
            body = error_body(code, detail.get("message"))
        elif code := _known_code(detail):
            body = error_body(code)
        else:
            return await http_exception_handler(request, exc)
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        code = ErrorCode.VALIDATION_ERROR
        return JSONResponse(error_body(code), status_code=HTTP_STATUS[code])

    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
