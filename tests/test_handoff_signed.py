"""무상태 서명 토큰 시험 — 서버 메모리가 비어도 교환되어야 한다(10/29 08:59 첫 클릭 실패 재발 방지)."""

import pytest
from fastapi.testclient import TestClient
from inheritance.kakao.handoff import router as handoff_router
from inheritance.kakao.handoff.repository import SignedHandoffStore
from inheritance.kakao.handoff.service import HandoffService
from inheritance.main import create_app

KEY = "k" * 40
OK = {
    "relationship": "descendant",
    "deathDate": "2026-09-30",
    "deathDateUnknown": False,
    "oneStopApplication": "unknown",
    "risks": [],
}
client = TestClient(create_app())


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("HANDOFF_SERVER_SECRET", "s" * 40)
    monkeypatch.setenv("HANDOFF_HASH_KEY", KEY)


def test_exchange_works_on_a_fresh_instance():
    # 발급한 인스턴스와 교환하는 인스턴스가 다른 상황(서버가 잠들었다 깨거나 인스턴스가 바뀜).
    now = [1000.0]
    a = SignedHandoffStore(clock=lambda: now[0])
    token = a.issue({"a": 1})
    b = SignedHandoffStore(clock=lambda: now[0] + 120)  # 2분 뒤, 메모리가 비어 있는 새 인스턴스
    assert b.consume(token) == {"a": 1}


def test_used_once_on_same_instance():
    s = SignedHandoffStore()
    token = s.issue({"a": 1})
    assert s.consume(token) == {"a": 1}
    assert s.consume(token) is None


def test_expired_after_ttl():
    now = [1000.0]
    s = SignedHandoffStore(ttl=600, clock=lambda: now[0])
    token = s.issue({"a": 1})
    now[0] = 1600.0
    assert s.consume(token) is None


def test_tampered_or_wrong_key_rejected():
    s = SignedHandoffStore(key="a" * 40)
    token = s.issue({"a": 1})
    body, sig = token.split(".")
    assert s.consume(f"{body}x.{sig}") is None
    assert s.consume(f"{body}.{sig[:-2]}ab") is None
    assert SignedHandoffStore(key="b" * 40).consume(token) is None
    assert s.consume("garbage") is None
    assert s.consume("") is None


def test_server_secret_is_not_used_as_signing_key(monkeypatch):
    # 카카오 서버와 나눠 쓰는 비밀값으로 서명하면 키 분리가 깨진다.
    monkeypatch.delenv("HANDOFF_HASH_KEY")
    with pytest.raises(ValueError):
        SignedHandoffStore().issue({"a": 1})


def test_http_flow_with_fresh_service(monkeypatch):
    monkeypatch.setattr(handoff_router, "service", HandoffService(SignedHandoffStore()))
    r = client.post("/api/handoff", json=OK, headers={"X-Handoff-Secret": "s" * 40})
    assert r.status_code == 200
    token = r.json()["token"]
    # 서버가 바뀐 것처럼 서비스를 새로 만든다.
    monkeypatch.setattr(handoff_router, "service", HandoffService(SignedHandoffStore()))
    ok = client.post("/api/handoff/exchange", json={"token": token})
    assert ok.status_code == 200
    assert ok.json() == OK
    again = client.post("/api/handoff/exchange", json={"token": token})
    assert again.status_code == 400
