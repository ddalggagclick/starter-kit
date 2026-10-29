# 담당: [C] | 책임: [C] 웹 일회성 연결 토큰 교환 HTTP 진입
# 구현할 기능: API 담당자 작성 OpenAPI와 연결; 만료·소모·오류 결과 동일 사용자 문구
# 코드 경계: 카카오→웹 토큰만 다룬다. JWT 로그인 인증 수단으로 사용하지 않는다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A04 `POST /api/handoff`, A05 `POST /api/handoff/exchange` (openapi.yaml 0.2.0).

오류 본문은 openapi의 Error 모양 {code, message}이고, 상태 번호는 core/errors.py의 HTTP_STATUS를 쓴다.
토큰 원문·비밀값·답변 내용은 로그에 남기지 않는다.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Header, HTTPException

from inheritance.core.errors import HTTP_STATUS, ErrorCode
from inheritance.kakao.handoff.models import ExchangeRequest, HandoffPayload, IssueResponse
from inheritance.kakao.handoff.repository import HANDOFF_TTL_SECONDS, SignedHandoffStore
from inheritance.kakao.handoff.service import HandoffInvalid, HandoffService, HandoffUnauthorized

# 무상태 서명 토큰: 서버가 잠들어도 토큰이 사라지지 않는다(10/29 팀 결정, 10/29 08:59 첫 클릭 실패 확인).
service = HandoffService(SignedHandoffStore())
router = APIRouter(prefix="/api/handoff", tags=["handoff"])
logger = logging.getLogger(__name__)


# 허용 필드(event·status·duration_ms)만 extra로 넘긴다(PRD 7-4-3). 토큰·비밀값·답변은 넘기지 않는다.
def _log(event: str, status: str, started: float) -> None:
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(event, extra={"event": event, "status": status, "duration_ms": duration_ms})


def _error(code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=HTTP_STATUS[code] or 500, detail={"code": code.value, "message": message}
    )


@router.post("", response_model=IssueResponse, response_model_by_alias=True)
def issue_handoff(
    body: HandoffPayload, x_handoff_secret: str | None = Header(default=None)
) -> IssueResponse:
    started = time.perf_counter()
    try:
        token = service.issue(body, x_handoff_secret)
    except HandoffUnauthorized:
        _log("handoff.issue", "unauthorized", started)
        # 비밀값 불일치는 401. 코드 이름은 openapi에서도 제안 상태라 UNAUTHENTICATED를 쓴다.
        raise _error(ErrorCode.UNAUTHENTICATED, "인증에 실패했습니다.") from None
    _log("handoff.issue", "issued", started)
    return IssueResponse(token=token, expires_in_seconds=HANDOFF_TTL_SECONDS)


@router.post("/exchange")
def exchange_handoff(body: ExchangeRequest) -> dict:
    started = time.perf_counter()
    try:
        payload = service.exchange(body.token)
    except HandoffInvalid:
        # 만료·이미 사용·없는 토큰을 로그에서도 구분하지 않는다(D1).
        _log("handoff.exchange", "invalid", started)
        raise _error(
            ErrorCode.HANDOFF_INVALID, "연결이 만료되었거나 이미 사용되었습니다."
        ) from None
    _log("handoff.exchange", "exchanged", started)
    return payload
