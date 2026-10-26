# 담당: [B] 제안 · 배치 승인: [통합] | 책임: A17 서버 체크리스트 API 시험.
# PRD: 4-6-2, 4-5-3, 4-6-3, 5-4-2 / 2026-10-26 팀 회의 결정.
# 구현할 기능: 동의·저장·조회·덮어쓰기·철회, 계정 분리, 탈퇴 시 삭제, CSRF·인증을 확인.
# 완료 기준: 실제 DB·메일 없이 통과.
"""A17 시험. 메모리 저장소와 시험용 메일 발송기만 쓴다."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from inheritance.auth.jwt import AccessTokenCodec
from inheritance.auth.repository import InMemoryAuthRepository
from inheritance.auth.router import create_auth_router
from inheritance.auth.service import AuthService
from inheritance.checklist.server_router import create_server_checklist_router
from inheritance.checklist.server_storage import MAX_BYTES, InMemoryServerChecklistStore
from inheritance.core.security import WebSecuritySettings
from inheritance.main import create_app

ORIGIN = "http://localhost:5173"
SECURITY = WebSecuritySettings(allowed_origins=(ORIGIN,), csrf_secret="c" * 32, production=False)
PASSWORD = "secret123"
# 프론트 #134의 itemStates 모양
ITEM = {
    "kind": "inheritance-checklist",
    "version": 1,
    "answers": {"relationship": "spouse", "deathDateUnknown": True},
    "riskAnswers": {"debt": {"answer": "yes"}},
    "procedureStates": {"p01": {"read": True}},
}


class Mail:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def send_verification(self, email: str, token: str) -> None:
        self.tokens.append(token)

    def send_password_reset(self, email: str, token: str) -> None:
        return None


class Env:
    def __init__(self) -> None:
        self.mail = Mail()
        self.store = InMemoryServerChecklistStore()
        self.auth = AuthService(InMemoryAuthRepository(), AccessTokenCodec("k" * 32), self.mail)
        self.auth.on_account_deleted(self.store.delete)
        app = create_app()
        app.include_router(create_auth_router(self.auth, SECURITY))
        app.include_router(create_server_checklist_router(self.store, self.auth, SECURITY))
        self.client = TestClient(app, headers={"Origin": ORIGIN})
        csrf = self.client.get("/api/auth/csrf").json()["csrfToken"]
        self.client.headers["X-CSRF-Token"] = csrf

    def login(self, email: str) -> dict[str, str]:
        self.client.post("/api/auth/signup", json={"email": email, "password": PASSWORD})
        token = self.mail.tokens[-1]
        self.client.post("/api/auth/email/verify", json={"verificationToken": token})
        access = self.client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["accessToken"]
        return {"Authorization": f"Bearer {access}"}

    def get(self, auth):
        return self.client.get("/api/me/checklist", headers=auth)

    def put(self, auth, item_states, consent=True):
        body = {"itemStates": item_states, "serverSaveConsent": consent}
        return self.client.put("/api/me/checklist", json=body, headers=auth)

    def delete(self, auth):
        return self.client.delete("/api/me/checklist", headers=auth)


@pytest.fixture
def env() -> Env:
    return Env()


def test_save_read_overwrite_and_withdraw(env):
    auth = env.login("a@example.com")
    # 미동의 조회는 본문 없이 403
    before = env.get(auth)
    assert before.status_code == 403 and before.json()["code"] == "FORBIDDEN"
    assert "itemStates" not in before.json()

    saved = env.put(auth, [ITEM])
    assert saved.status_code == 200
    assert saved.json() == {"itemStates": [ITEM], "serverSaveConsent": True}
    assert env.get(auth).json()["itemStates"] == [ITEM]

    # 전체 덮어쓰기: 이전 기록과 합치지 않는다
    changed = {**ITEM, "procedureStates": {"p02": {"read": True}}}
    env.put(auth, [changed])
    assert env.get(auth).json()["itemStates"] == [changed]

    # 철회 = 삭제, 다시 지워도 같은 결과
    assert env.delete(auth).status_code == 204
    assert env.delete(auth).status_code == 204
    assert env.get(auth).status_code == 403


def test_accounts_are_isolated(env):
    a, b = env.login("a@example.com"), env.login("b@example.com")
    env.put(a, [ITEM])
    assert env.get(b).status_code == 403
    env.delete(b)
    assert env.get(a).status_code == 200


def test_put_without_consent_is_403(env):
    auth = env.login("a@example.com")
    response = env.put(auth, [ITEM], consent=False)
    assert response.status_code == 403
    assert env.get(auth).status_code == 403


@pytest.mark.parametrize(
    "item_states",
    [
        ["문자열"],
        [ITEM] * 21,
        [{"blob": "가" * (MAX_BYTES // 3 + 10)}],
    ],
)
def test_bad_item_states_are_422(env, item_states):
    auth = env.login("a@example.com")
    response = env.put(auth, item_states)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"


def test_requires_login_and_csrf(env):
    assert env.get({}).status_code == 401
    assert env.get({"Authorization": "Bearer wrong"}).status_code == 401
    auth = env.login("a@example.com")
    no_csrf = env.client.put(
        "/api/me/checklist",
        json={"itemStates": [ITEM], "serverSaveConsent": True},
        headers={**auth, "X-CSRF-Token": ""},
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "CSRF_INVALID"


def test_account_deletion_removes_server_checklist(env):
    auth = env.login("a@example.com")
    env.put(auth, [ITEM])
    response = env.client.request(
        "DELETE", "/api/account", json={"password": PASSWORD}, headers=auth
    )
    assert response.json()["checklist"] == "deleted"
    assert env.store.get(env.auth.user_id_from_access(auth["Authorization"][7:])) is None


def test_app_wires_a17_only_with_auth_secrets(monkeypatch):
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    monkeypatch.delenv("CSRF_SECRET", raising=False)
    assert TestClient(create_app()).get("/api/me/checklist").status_code == 404
    monkeypatch.setenv("JWT_SIGNING_KEY", "j" * 32)
    monkeypatch.setenv("CSRF_SECRET", "c" * 32)
    assert TestClient(create_app()).get("/api/me/checklist").status_code == 401
