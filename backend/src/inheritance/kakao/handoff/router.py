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

from fastapi import APIRouter, Header, HTTPException

from inheritance.core.errors import HTTP_STATUS, ErrorCode
from inheritance.kakao.handoff.models import ExchangeRequest, HandoffPayload, IssueResponse
from inheritance.kakao.handoff.repository import HANDOFF_TTL_SECONDS, InMemoryHandoffStore
from inheritance.kakao.handoff.service import HandoffInvalid, HandoffService, HandoffUnauthorized

service = HandoffService(InMemoryHandoffStore())
router = APIRouter(prefix="/api/handoff", tags=["handoff"])


def _error(code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=HTTP_STATUS[code] or 500, detail={"code": code.value, "message": message}
    )


@router.post("", response_model=IssueResponse, response_model_by_alias=True)
def issue_handoff(
    body: HandoffPayload, x_handoff_secret: str | None = Header(default=None)
) -> IssueResponse:
    try:
        token = service.issue(body, x_handoff_secret)
    except HandoffUnauthorized:
        # 비밀값 불일치는 401. 코드 이름은 openapi에서도 제안 상태라 UNAUTHENTICATED를 쓴다.
        raise _error(ErrorCode.UNAUTHENTICATED, "인증에 실패했습니다.") from None
    return IssueResponse(token=token, expires_in_seconds=HANDOFF_TTL_SECONDS)


@router.post("/exchange")
def exchange_handoff(body: ExchangeRequest) -> dict:
    try:
        return service.exchange(body.token)
    except HandoffInvalid:
        raise _error(
            ErrorCode.HANDOFF_INVALID, "연결이 만료되었거나 이미 사용되었습니다."
        ) from None
