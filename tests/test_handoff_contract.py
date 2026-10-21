"""A04·A05 인계 계약 시험 (openapi.yaml 0.2.0, D1, PRD 1-4-2)."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inheritance.kakao.handoff import router as handoff_router
from inheritance.kakao.handoff.repository import InMemoryHandoffStore
from inheritance.kakao.handoff.service import HandoffService

SECRET = "test-secret"
OK = {
    "relationship": "descendant",
    "deathDate": "2026-09-30",
    "deathDateUnknown": False,
    "oneStopApplication": "unknown",
    "risks": [{"riskId": "property_disposal", "answer": "yes"}],
}

app = FastAPI()
app.include_router(handoff_router.router)
client = TestClient(app)


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
    assert second.json()["detail"]["code"] == "HANDOFF_INVALID"


def test_unknown_token_same_error_as_used():
    r = exchange("not-a-real-token")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "HANDOFF_INVALID"


def test_wrong_missing_or_unset_secret(monkeypatch):
    assert issue(secret="nope").status_code == 401
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
    assert issue({**OK, **patch}).status_code == 422


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
