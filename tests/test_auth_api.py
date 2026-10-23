# 담당: [B] 제안 · 배치 승인: [통합] | 책임: A11~A16 인증 API 계약 시험.
# PRD: E5 / 5-2, 5-3 / openapi.yaml auth·account.
# 구현할 기능: 가입→인증→로그인→갱신(회전·재사용 탐지)→로그아웃, 재설정, 탈퇴, CSRF, 제한을 확인.
# 완료 기준: 실제 메일·DB 없이 통과. 메일은 시험용 발송기로 토큰을 받는다.
"""인증 API 시험. 메모리 저장소와 시험용 메일 발송기만 쓴다."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from inheritance.auth.jwt import AccessTokenCodec
from inheritance.auth.repository import InMemoryAuthRepository
from inheritance.auth.router import auth_router_from_env, create_auth_router
from inheritance.auth.service import AuthService
from inheritance.core.security import WebSecuritySettings
from inheritance.main import create_app

ORIGIN = "http://localhost:5173"
SECURITY = WebSecuritySettings(allowed_origins=(ORIGIN,), csrf_secret="c" * 32, production=False)
REFRESH = SECURITY.refresh_cookie_name
EMAIL = "user@example.com"
PASSWORD = "secret123"


class RecordingEmail:
    def __init__(self) -> None:
        self.verifications: list[tuple[str, str]] = []
        self.resets: list[tuple[str, str]] = []

    def send_verification(self, email: str, token: str) -> None:
        self.verifications.append((email, token))

    def send_password_reset(self, email: str, token: str) -> None:
        self.resets.append((email, token))


class Env:
    def __init__(self) -> None:
        self.now = time.time()
        self.mail = RecordingEmail()
        self.repo = InMemoryAuthRepository()
        service = AuthService(
            self.repo, AccessTokenCodec("k" * 32), self.mail, clock=lambda: self.now
        )
        app = create_app()
        app.include_router(create_auth_router(service, SECURITY))
        self.client = TestClient(app, headers={"Origin": ORIGIN})
        csrf = self.client.get("/api/auth/csrf").json()["csrfToken"]
        self.client.headers["X-CSRF-Token"] = csrf

    def post(self, path: str, body: dict | None = None):
        return self.client.post(path, json=body)

    def signup_verified(self, email: str = EMAIL, password: str = PASSWORD) -> None:
        assert (
            self.post("/api/auth/signup", {"email": email, "password": password}).status_code == 201
        )
        token = self.mail.verifications[-1][1]
        assert self.post("/api/auth/email/verify", {"verificationToken": token}).status_code == 200

    def login(self, email: str = EMAIL, password: str = PASSWORD):
        return self.post("/api/auth/login", {"email": email, "password": password})


@pytest.fixture
def env() -> Env:
    return Env()


def code(response) -> str:
    return response.json()["code"]


def test_signup_verify_login_refresh_logout(env):
    assert env.post("/api/auth/signup", {"email": EMAIL, "password": PASSWORD}).status_code == 201
    # 인증 전 로그인은 401(비밀번호가 맞을 때만 인증 필요 문구).
    before = env.login()
    assert before.status_code == 401 and code(before) == "UNAUTHENTICATED"
    assert "인증" in before.json()["message"]

    token = env.mail.verifications[-1][1]
    assert env.post("/api/auth/email/verify", {"verificationToken": token}).status_code == 200
    reused = env.post("/api/auth/email/verify", {"verificationToken": token})
    assert reused.status_code == 400 and code(reused) == "TOKEN_INVALID"

    login = env.login()
    assert login.status_code == 200
    assert login.json()["expiresIn"] == 900 and login.json()["accessToken"]
    assert "httponly" in login.headers["set-cookie"].lower()
    first_refresh = env.client.cookies[REFRESH]

    refreshed = env.post("/api/auth/refresh")
    assert refreshed.status_code == 200 and refreshed.json()["accessToken"]
    assert env.client.cookies[REFRESH] != first_refresh

    assert env.post("/api/auth/logout").status_code == 204
    after = env.post("/api/auth/refresh")
    assert after.status_code == 401 and code(after) == "REFRESH_INVALID"


def test_reused_refresh_token_revokes_whole_family(env):
    env.signup_verified()
    env.login()
    old = env.client.cookies[REFRESH]
    assert env.post("/api/auth/refresh").status_code == 200
    rotated = env.client.cookies[REFRESH]

    env.client.cookies.set(REFRESH, old)
    stolen = env.post("/api/auth/refresh")
    assert stolen.status_code == 401 and code(stolen) == "REFRESH_INVALID"
    # 재사용이 탐지되면 정상 쪽 최신 토큰도 끊긴다.
    env.client.cookies.set(REFRESH, rotated)
    assert env.post("/api/auth/refresh").status_code == 401


def test_duplicate_email_is_409_case_insensitive(env):
    env.signup_verified()
    again = env.post("/api/auth/signup", {"email": "USER@Example.com", "password": PASSWORD})
    assert again.status_code == 409 and code(again) == "EMAIL_TAKEN"


@pytest.mark.parametrize("password", ["abcdefgh", "12345678", "abc123", "a1" * 33])
def test_password_policy_is_422(env, password):
    response = env.post("/api/auth/signup", {"email": EMAIL, "password": password})
    assert response.status_code == 422 and code(response) == "VALIDATION_ERROR"


def test_csrf_and_origin_are_required(env):
    body = {"email": EMAIL, "password": PASSWORD}
    no_header = env.client.post(
        "/api/auth/signup", json=body, headers={"X-CSRF-Token": "", "Origin": ORIGIN}
    )
    assert no_header.status_code == 403 and code(no_header) == "CSRF_INVALID"
    other_origin = env.client.post(
        "/api/auth/signup", json=body, headers={"Origin": "https://evil.example.com"}
    )
    assert other_origin.status_code == 403 and code(other_origin) == "ORIGIN_FORBIDDEN"


def test_five_failed_logins_lock_for_fifteen_minutes(env):
    env.signup_verified()
    for _ in range(5):
        assert env.login(password="wrong123").status_code == 401
    locked = env.login()
    assert locked.status_code == 429 and code(locked) == "RATE_LIMITED"
    env.now += 15 * 60
    assert env.login().status_code == 200


def test_resend_hides_signup_and_limits_rate(env):
    unknown = env.post("/api/auth/email/resend", {"email": "nobody@example.com"})
    assert unknown.status_code == 202 and env.mail.verifications == []

    env.post("/api/auth/signup", {"email": EMAIL, "password": PASSWORD})
    assert env.post("/api/auth/email/resend", {"email": EMAIL}).status_code == 202
    too_soon = env.post("/api/auth/email/resend", {"email": EMAIL})
    assert too_soon.status_code == 429 and code(too_soon) == "RATE_LIMITED"
    for _ in range(4):
        env.now += 61
        env.post("/api/auth/email/resend", {"email": EMAIL})
    env.now += 61
    # 하루 5회를 넘으면 간격이 지나도 막힌다.
    assert env.post("/api/auth/email/resend", {"email": EMAIL}).status_code == 429


def test_verification_link_expires_after_24_hours(env):
    env.post("/api/auth/signup", {"email": EMAIL, "password": PASSWORD})
    env.now += 24 * 60 * 60
    token = env.mail.verifications[-1][1]
    expired = env.post("/api/auth/email/verify", {"verificationToken": token})
    assert expired.status_code == 400 and code(expired) == "TOKEN_INVALID"


def test_password_reset_logs_out_everywhere(env):
    env.signup_verified()
    env.login()
    assert (
        env.post("/api/auth/password/reset-request", {"email": "nobody@example.com"}).status_code
        == 202
    )
    assert env.mail.resets == []

    assert env.post("/api/auth/password/reset-request", {"email": EMAIL}).status_code == 202
    token = env.mail.resets[-1][1]
    done = env.post("/api/auth/password/reset", {"resetToken": token, "newPassword": "newpass456"})
    assert done.status_code == 200
    assert env.post("/api/auth/refresh").status_code == 401
    assert env.login(password=PASSWORD).status_code == 401
    assert env.login(password="newpass456").status_code == 200
    reused = env.post("/api/auth/password/reset", {"resetToken": token, "newPassword": "other789x"})
    assert reused.status_code == 400 and code(reused) == "TOKEN_INVALID"


def test_reset_link_expires_after_30_minutes(env):
    env.signup_verified()
    env.post("/api/auth/password/reset-request", {"email": EMAIL})
    env.now += 30 * 60
    token = env.mail.resets[-1][1]
    response = env.post(
        "/api/auth/password/reset", {"resetToken": token, "newPassword": "newpass456"}
    )
    assert response.status_code == 400


def test_delete_account_requires_access_and_password(env):
    env.signup_verified()
    access = env.login().json()["accessToken"]

    def delete(password: str, token: str | None = access):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return env.client.request(
            "DELETE", "/api/account", json={"password": password}, headers=headers
        )

    assert code(delete(PASSWORD, None)) == "UNAUTHENTICATED"
    assert delete(PASSWORD, access + "x").status_code == 401
    wrong = delete("wrong123")
    assert wrong.status_code == 403 and code(wrong) == "FORBIDDEN"
    done = delete(PASSWORD)
    assert done.status_code == 200 and done.json()["account"] == "deleted"
    assert env.login().status_code == 401
    assert env.post("/api/auth/refresh").status_code == 401


def test_raw_password_and_tokens_are_not_stored(env):
    env.signup_verified()
    env.login()
    stored = repr(vars(env.repo))
    assert PASSWORD not in stored
    assert env.client.cookies[REFRESH] not in stored
    assert all(token not in stored for _, token in env.mail.verifications)


def test_auth_routes_closed_without_secrets(monkeypatch):
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    monkeypatch.delenv("CSRF_SECRET", raising=False)
    assert auth_router_from_env() is None
    assert TestClient(create_app()).post("/api/auth/login", json={}).status_code == 404
    monkeypatch.setenv("JWT_SIGNING_KEY", "j" * 32)
    monkeypatch.setenv("CSRF_SECRET", "c" * 32)
    assert auth_router_from_env() is not None
