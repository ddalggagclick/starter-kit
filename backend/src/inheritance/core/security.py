"""공통 인증 보안 보일러플레이트 (검토본).

담당: 통합 관리자.
책임: 별도 Origin의 React Static Site와 Render FastAPI 간 CORS·쿠키·CSRF 정책.
구현할 기능: 허용 Origin 검사, 서명된 이중 제출 CSRF, Refresh 쿠키 발급·삭제.
경계: JWT 검증/Refresh DB 회전은 auth.service, 실제 HTTP 경로는 API 담당자.
완료 기준: 허용/거부 Origin, 위조·누락 토큰, HTTPS Cookie, 로컬 개발 예외 테스트.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .origin import is_exact_http_origin


@dataclass(frozen=True)
class WebSecuritySettings:
    """배포 환경의 허용 주소만 설정. 와일드카드 CORS 금지."""

    allowed_origins: tuple[str, ...]
    csrf_secret: str
    production: bool = True
    # Render 기본 *.onrender.com 2개는 별도 site일 수 있으므로 SameSite=None 사용.
    # Chrome/Firefox/Safari에서 third-party cookie 차단이 가능하므로 실환경 검증 필수.
    csrf_ttl_seconds: int = 3600
    refresh_ttl_seconds: int = 7 * 24 * 60 * 60

    def __post_init__(self) -> None:
        if not self.allowed_origins or any(
            not is_exact_http_origin(s) for s in self.allowed_origins
        ):
            raise ValueError("CORS must use exact http(s) origins without a path or wildcard")
        if len(self.csrf_secret) < 32:
            raise ValueError("CSRF secret must be at least 32 characters")
        if self.production and any(not s.startswith("https://") for s in self.allowed_origins):
            raise ValueError("production origins must use HTTPS")
        if self.csrf_ttl_seconds < 60:
            raise ValueError("CSRF TTL must be at least one minute")

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-inheritance-csrf" if self.production else "inheritance-csrf-dev"

    @property
    def refresh_cookie_name(self) -> str:
        return "__Host-inheritance-refresh" if self.production else "inheritance-refresh-dev"

    @property
    def same_site(self) -> str:
        return "none" if self.production else "lax"


def install_cors(app: FastAPI, settings: WebSecuritySettings) -> None:
    """승인된 인증 보안 설정의 정확한 Origin을 CORS에 적용한다."""
    install_cors_origins(app, settings.allowed_origins)


def install_cors_origins(app: FastAPI, origins: tuple[str, ...]) -> None:
    """Health-only 진입도 비밀키/DB 없이 정확한 Origin CORS를 설치한다."""
    if not origins or any(not is_exact_http_origin(origin) for origin in origins):
        raise ValueError("FRONTEND_ORIGIN must be an exact http(s) origin")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )


def _signature(secret: str, stamp: str, nonce: str) -> str:
    return hmac.new(secret.encode(), f"{stamp}.{nonce}".encode(), hashlib.sha256).hexdigest()


# 발급 시각과 난수를 비밀키로 서명해 서버 세션 저장 없이 검증할 CSRF 토큰을 만든다.
def new_csrf_token(settings: WebSecuritySettings, *, now: int | None = None) -> str:
    stamp = str(int(time.time()) if now is None else now)
    nonce = base64.urlsafe_b64encode(secrets.token_bytes(24)).rstrip(b"=").decode()
    return f"{stamp}.{nonce}.{_signature(settings.csrf_secret, stamp, nonce)}"


# 형식·발급 시각·만료 시간을 확인하고 HMAC을 상수 시간 비교해 위조 토큰을 거부한다.
def valid_csrf_token(settings: WebSecuritySettings, token: str, *, now: int | None = None) -> bool:
    try:
        stamp, nonce, mac = token.split(".")
        issued = int(stamp)
        current = int(time.time()) if now is None else now
        if issued > current + 30 or current - issued > settings.csrf_ttl_seconds:
            return False
        return hmac.compare_digest(mac, _signature(settings.csrf_secret, stamp, nonce))
    except (ValueError, TypeError, AttributeError):
        return False


def require_allowed_origin(request: Request, settings: WebSecuritySettings) -> None:
    # 브라우저의 POST·Refresh·CSRF 발급에 사용. Origin 누락 요청도 실패 처리.
    if request.headers.get("origin") not in settings.allowed_origins:
        raise HTTPException(status_code=403, detail="ORIGIN_FORBIDDEN")


def issue_csrf(
    request: Request, response: Response, settings: WebSecuritySettings
) -> dict[str, str]:
    """GET CSRF-bootstrap에 호출. 응답 본문으로 토큰을 전달해 타 도메인 프론트가 읽도록 한다.

    API 측의 HttpOnly CSRF 쿠키는 브라우저 JS에서 읽지 않는다. GET 응답은 no-store.
    """
    require_allowed_origin(request, settings)
    token = request.cookies.get(settings.csrf_cookie_name, "")
    # 기존 토큰을 재사용해 브라우저 쿠키와 응답 본문의 CSRF 값이 계속 일치하게 한다.
    if not valid_csrf_token(settings, token):
        token = new_csrf_token(settings)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        httponly=True,
        secure=settings.production,
        samesite=settings.same_site,
        path="/",
        max_age=settings.csrf_ttl_seconds,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"csrfToken": token}


def enforce_csrf(request: Request, settings: WebSecuritySettings) -> None:
    """쿠키 기반 인증의 모든 상태 변경 라우트에 Depends로 명시적으로 지정.

    예: 로그인·가입·갱신·로그아웃. API 담당자가 실제 경로/Depends 연결.
    """
    require_allowed_origin(request, settings)
    cookie = request.cookies.get(settings.csrf_cookie_name, "")
    header = request.headers.get("x-csrf-token", "")
    # 쿠키가 자동 전송된 것만으로는 부족하다. 허용 Origin의 요청이 같은 서명 토큰을 헤더로 보내야 한다.
    if not (
        cookie
        and header
        and hmac.compare_digest(cookie, header)
        and valid_csrf_token(settings, cookie)
    ):
        raise HTTPException(status_code=403, detail="CSRF_INVALID")


def set_refresh_cookie(
    response: Response, refresh_token: str, settings: WebSecuritySettings
) -> None:
    """auth.service가 발급·회전한 토큰만 받는다. 원문 로그 출력 금지."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.production,
        samesite=settings.same_site,
        path="/",
        max_age=settings.refresh_ttl_seconds,
    )
    response.headers["Cache-Control"] = "no-store"


def clear_refresh_cookie(response: Response, settings: WebSecuritySettings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/",
        secure=settings.production,
        httponly=True,
        samesite=settings.same_site,
    )


def web_security_from_settings(config: Settings) -> WebSecuritySettings:
    """Composition root에서 Settings와 인증 보안 정책을 하나로 연결. 실제 라우트 연결은 별도."""
    return WebSecuritySettings(
        allowed_origins=(config.frontend_origin,),
        csrf_secret=config.csrf_secret,
        production=config.production,
        refresh_ttl_seconds=config.refresh_token_ttl_seconds,
    )
