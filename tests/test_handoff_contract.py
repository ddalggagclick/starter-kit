"""A04·A05 인계 계약 시험 (openapi.yaml 0.2.0, D1, PRD 1-4-2)."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from inheritance.kakao.handoff import router as handoff_router
from inheritance.kakao.handoff.repository import InMemoryHandoffStore
from inheritance.kakao.handoff.service import HandoffService
from inheritance.main import create_app

SECRET = "test-secret"
OK = {
    "relationship": "descendant",
    "deathDate": "2026-09-30",
    "deathDateUnknown": False,
    "oneStopApplication": "unknown",
    "risks": [{"riskId": "property_disposal", "answer": "yes"}],
}

# main.py와 같은 앱(라우터·오류 처리기 연결)으로 시험한다.
client = TestClient(create_app())
INVALID = {"code": "HANDOFF_INVALID", "message": "연결이 만료되었거나 이미 사용되었습니다."}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("HANDOFF_SERVER_SECRET", SECRET)
    monkeypatch.setattr(handoff_router, "service", HandoffService(InMemoryHandoffStore()))


def issue(body=OK, secret=SECRET):
    return client.post("/api/handoff", json=body, headers={"X-Handoff-Secret": secret})


def exchange(token):
    return client.post("/api/handoff/exchange", json={"token": token})


def test_issue_and_exchange_once():
    r = issue()
    assert r.status_code == 200
    assert r.json()["expiresInSeconds"] == 600
    token = r.json()["token"]
    first = exchange(token)
    assert first.status_code == 200
    assert first.json() == OK
    second = exchange(token)
    assert second.status_code == 400
    assert second.json() == INVALID


def test_unknown_token_same_error_as_used():
    r = exchange("not-a-real-token")
    assert r.status_code == 400
    assert r.json() == INVALID


def test_wrong_missing_or_unset_secret(monkeypatch):
    r = issue(secret="nope")
    assert r.status_code == 401
    assert r.json() == {"code": "UNAUTHENTICATED", "message": "인증에 실패했습니다."}
    assert client.post("/api/handoff", json=OK).status_code == 401
    monkeypatch.delenv("HANDOFF_SERVER_SECRET")
    assert issue(secret="").status_code == 401


@pytest.mark.parametrize(
    "patch",
    [
        {"relationship": "child_grandchild"},
        {"deathDate": None, "deathDateUnknown": False},
        {"deathDate": "2026-09-30", "deathDateUnknown": True},
        {"deathDate": "2999-01-01"},
        {"oneStopApplication": "applied"},
        {"risks": [{"riskId": "debt", "answer": True}]},
        {"risks": [{"riskId": "debtGuarantee", "answer": "yes"}]},
        {"risks": [{"riskId": "debt", "answer": "yes"}, {"riskId": "debt", "answer": "no"}]},
        {"extra": 1},
    ],
)
def test_validation_422(patch):
    r = issue({**OK, **patch})
    assert r.status_code == 422
    # openapi Error 모양이며, 보낸 입력값을 본문에 되돌려 주지 않는다.
    assert r.json() == {"code": "VALIDATION_ERROR", "message": "VALIDATION_ERROR"}


def test_exchange_validation_422():
    r = client.post("/api/handoff/exchange", json={})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_unknown_death_date_and_no_risks():
    body = {**OK, "deathDate": None, "deathDateUnknown": True, "risks": []}
    got = exchange(issue(body).json()["token"]).json()
    assert got == body


def test_expired():
    now = [0.0]
    store = InMemoryHandoffStore(clock=lambda: now[0])
    token = store.issue({"a": 1})
    now[0] = 600.0
    assert store.consume(token) is None


def test_unconsumed_expired_answers_are_purged():
    now = [0.0]
    store = InMemoryHandoffStore(clock=lambda: now[0])
    store.issue({"a": 1})
    store.issue({"b": 2})
    now[0] = 600.0
    # 발급 요청이 없어도 교환 요청 때 만료 답변을 모두 지운다.
    store.consume("not-a-real-token")
    assert len(store) == 0

    store.issue({"c": 3})
    now[0] = 1200.0
    # 요청이 전혀 없을 때는 앱 수명주기의 주기 작업이 purge_expired를 부른다.
    store.purge_expired()
    assert len(store) == 0


def test_app_lifespan_purges_periodically(monkeypatch):
    from inheritance import main

    calls = []

    class Spy:
        def purge_expired(self):
            calls.append(1)

    monkeypatch.setattr(main, "HANDOFF_PURGE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(handoff_router, "service", Spy())
    with TestClient(create_app()) as running:
        assert running.get("/health").status_code == 200
        for _ in range(100):
            if calls:
                break
            time.sleep(0.01)
    assert calls


def test_concurrent_exchange_only_one_wins():
    store = InMemoryHandoffStore()
    for _ in range(50):
        token = store.issue({"a": 1})
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(store.consume, [token] * 8))
        assert sum(r is not None for r in results) == 1


def test_raw_token_not_kept():
    store = InMemoryHandoffStore()
    token = store.issue({})
    assert token not in store._items


# PRD 7-4-3: 인계 로그에는 event·status·duration_ms만 넘기고 토큰·비밀값·답변 값은 넘기지 않는다(#87).
def test_handoff_logs_only_safe_fields(caplog):
    caplog.set_level(logging.INFO, logger=handoff_router.logger.name)
    token = issue().json()["token"]
    exchange(token)
    exchange(token)
    issue(secret="wrong-secret-value")

    records = [r for r in caplog.records if r.name == handoff_router.logger.name]
    assert [(r.event, r.status) for r in records] == [
        ("handoff.issue", "issued"),
        ("handoff.exchange", "exchanged"),
        ("handoff.exchange", "invalid"),
        ("handoff.issue", "unauthorized"),
    ]
    forbidden = (
        token,
        SECRET,
        "wrong-secret-value",
        "descendant",
        "2026-09-30",
        "property_disposal",
    )
    for r in records:
        assert r.args == () and r.getMessage() == r.event
        assert isinstance(r.duration_ms, float) and r.duration_ms >= 0
        dumped = repr(vars(r))
        assert not any(value in dumped for value in forbidden)
