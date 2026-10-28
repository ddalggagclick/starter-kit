"""공통 오류 종류와 HTTP 변환 계약 (검토본).

담당: 통합 관리자. 책임: 예측 가능한 내부 오류를 코드·HTTP 상태에 매핑.
구현할 기능: 오류 분류, 요청 ID, 공개 가능한 메시지 키, 재시도 가능 여부.
경계: S7은 정상 HTTP 200의 판단 유보 결과이며 기술 오류가 아니다.
완료 기준: 각 코드의 HTTP 상태와 예상 공개 행동에 대한 계약 테스트.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
