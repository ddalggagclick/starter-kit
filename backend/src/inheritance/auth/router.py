# 담당: [통합] | 책임: [통합] 가입·로그인·토큰 갱신·로그아웃·내 정보 HTTP 진입
# 구현할 기능: API 담당자가 확정한 OpenAPI DTO 사용; HTTP 상태·쿠키/CSRF 경계
# 코드 경계: 계정·토큰·세션만 다룬다. 상속 규칙·채팅 원문을 저장하지 않는다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A11~A16 HTTP 진입과 CSRF 발급(GET /api/auth/csrf, 2026-10-23 API 담당 제안).

브라우저의 상태 변경 요청은 모두 허용 Origin + 서명 CSRF 쿠키·헤더 일치(core/security.py)를 확인한다.
Refresh는 HttpOnly 쿠키로만 주고받는다. 비밀번호·토큰은 로그와 오류 본문에 넣지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from inheritance.auth.email_sender import smtp_sender_from_env
from inheritance.auth.jwt import AccessTokenCodec, AccessTokenInvalid
from inheritance.auth.repository import InMemoryAuthRepository
from inheritance.auth.schemas import (
    CsrfResponse,
    DeleteAccountRequest,
    EmailRequest,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from inheritance.auth.service import AuthError, AuthService
from inheritance.core.errors import HTTP_STATUS, ErrorCode
from inheritance.core.origin import DEFAULT_FRONTEND_ORIGIN
from inheritance.core.security import (
    WebSecuritySettings,
    clear_refresh_cookie,
    enforce_csrf,
    issue_csrf,
    set_refresh_cookie,
)

_REASON_CODES = {
    "validation": ErrorCode.VALIDATION_ERROR,
    "email_taken": ErrorCode.EMAIL_TAKEN,
    "token_invalid": ErrorCode.TOKEN_INVALID,
    "rate_limited": ErrorCode.RATE_LIMITED,
    "unauthenticated": ErrorCode.UNAUTHENTICATED,
    "not_verified": ErrorCode.UNAUTHENTICATED,
    "refresh_invalid": ErrorCode.REFRESH_INVALID,
    "forbidden": ErrorCode.FORBIDDEN,
}
# 비밀번호가 맞은 뒤에만 나오는 경우라 가입 여부를 새로 알려 주지 않는다.
_NOT_VERIFIED_MESSAGE = "이메일 인증 후 로그인할 수 있습니다."


def _http_error(error: AuthError) -> HTTPException:
    code = _REASON_CODES[error.reason]
    detail = {"code": code.value}
    if error.reason == "not_verified":
        detail["message"] = _NOT_VERIFIED_MESSAGE
    return HTTPException(HTTP_STATUS[code] or 500, detail=detail)


def _run(action: Callable[..., Any], *args: Any) -> Any:
    try:
        return action(*args)
    except AuthError as error:
        raise _http_error(error) from None


# Authorization: Bearer 토큰에서 사용자 ID를 꺼낸다. 없거나 틀리면 401 UNAUTHENTICATED.
def user_id_from_bearer(service: AuthService, authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _http_error(AuthError("unauthenticated"))
    try:
        return service.user_id_from_access(token)
    except AccessTokenInvalid:
        raise _http_error(AuthError("unauthenticated")) from None


def create_auth_router(service: AuthService, security: WebSecuritySettings) -> APIRouter:
    router = APIRouter(tags=["auth"])

    def csrf(request: Request) -> None:
        enforce_csrf(request, security)

    checked = [Depends(csrf)]

    @router.get("/api/auth/csrf", response_model=CsrfResponse, operation_id="auth_csrf")
    def get_csrf(request: Request, response: Response) -> dict[str, str]:
        return issue_csrf(request, response, security)

    @router.post(
        "/api/auth/signup", status_code=201, operation_id="A11_signup", dependencies=checked
    )
    def signup(body: SignupRequest) -> Response:
        _run(service.signup, body.email, body.password)
        return Response(status_code=201)

    @router.post("/api/auth/email/verify", operation_id="A12_verifyEmail", dependencies=checked)
    def verify_email(body: VerifyEmailRequest) -> Response:
        _run(service.verify_email, body.verification_token)
        return Response(status_code=200)

    @router.post(
        "/api/auth/email/resend",
        status_code=202,
        operation_id="A12_resendEmail",
        dependencies=checked,
    )
    def resend_email(body: EmailRequest) -> Response:
        _run(service.resend_verification, body.email)
        return Response(status_code=202)

    @router.post(
        "/api/auth/login",
        response_model=LoginResponse,
        operation_id="A13_login",
        dependencies=checked,
    )
    def login(body: LoginRequest, response: Response) -> LoginResponse:
        tokens = _run(service.login, body.email, body.password)
        set_refresh_cookie(response, tokens.refresh_token, security)
        return LoginResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)

    @router.post(
        "/api/auth/refresh",
        response_model=RefreshResponse,
        operation_id="A14_refresh",
        dependencies=checked,
    )
    def refresh(request: Request, response: Response) -> RefreshResponse:
        tokens = _run(service.refresh, request.cookies.get(security.refresh_cookie_name))
        set_refresh_cookie(response, tokens.refresh_token, security)
        return RefreshResponse(access_token=tokens.access_token)

    @router.post(
        "/api/auth/logout", status_code=204, operation_id="A14_logout", dependencies=checked
    )
    def logout(request: Request) -> Response:
        service.logout(request.cookies.get(security.refresh_cookie_name))
        response = Response(status_code=204)
        clear_refresh_cookie(response, security)
        return response

    @router.post(
        "/api/auth/password/reset-request",
        status_code=202,
        operation_id="A15_resetRequest",
        dependencies=checked,
    )
    def reset_request(body: EmailRequest) -> Response:
        _run(service.request_password_reset, body.email)
        return Response(status_code=202)

    @router.post("/api/auth/password/reset", operation_id="A15_resetPassword", dependencies=checked)
    def reset_password(body: ResetPasswordRequest) -> Response:
        _run(service.reset_password, body.reset_token, body.new_password)
        return Response(status_code=200)

    @router.delete("/api/account", operation_id="A16_deleteAccount", dependencies=checked)
    def delete_account(
        body: DeleteAccountRequest,
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        user_id = user_id_from_bearer(service, authorization)
        _run(service.delete_account, user_id, body.password)
        clear_refresh_cookie(response, security)
        # 응답 모양은 openapi에 없어 제안 값이다. A17이 연결돼 있으면 서버 체크리스트도 함께 지운다.
        checklist = "deleted" if service.deletes_server_checklist else "not_stored"
        return {"account": "deleted", "sessions": "deleted", "checklist": checklist}

    return router


# JWT·CSRF 비밀값(32자 이상)이 없으면 인증 경로를 열지 않는다(None → main이 라우터를 붙이지 않음).
def auth_router_from_env() -> APIRouter | None:
    auth = auth_service_from_env()
    return create_auth_router(*auth) if auth is not None else None


# 인증 서비스와 보안 설정을 한 번 만든다. A17·A08도 같은 서비스로 Access 토큰을 확인한다.
def auth_service_from_env() -> tuple[AuthService, WebSecuritySettings] | None:
    signing_key = os.environ.get("JWT_SIGNING_KEY", "")
    csrf_secret = os.environ.get("CSRF_SECRET", "")
    if len(signing_key) < 32 or len(csrf_secret) < 32:
        return None
    origin = os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN)
    security = WebSecuritySettings(
        allowed_origins=(origin,),
        csrf_secret=csrf_secret,
        production=os.environ.get("APP_ENV", "development") == "production",
    )
    # SMTP 설정이 없으면 메일을 보내지 않는다(NoEmailSender).
    email = smtp_sender_from_env(origin)
    service = AuthService(InMemoryAuthRepository(), AccessTokenCodec(signing_key), email)
    return service, security
