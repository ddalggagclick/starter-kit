# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 실행 진입점(backend/app_entry.py) 조립 시험.
# 구현할 기능: 부품이 모두 있으면 A08이 답하고, 하나라도 없으면 503인지 확인한다.
# 완료 기준: 실제 Gemini·RAG·법령 호출 없이 통과.
"""실행 진입점 시험. Fake 모델과 시험용 검색·법령만 쓴다."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inheritance.contracts.law import LawLookupResult, LawQuery
from starter_llm.providers.fake import FakeModel
from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import app_entry

RAG = Evidence(
    evidence_id="rag-1",
    source=SourceRef("guide-1", "상속 절차 안내", "https://www.example.go.kr/guide", "기관", "v1"),
    text="상속 절차 안내",
    location="1쪽",
)


class Search:
    async def search(self, request: SearchRequest) -> SearchResult:
        return SearchResult((RAG,))


class Law:
    async def lookup(self, query: LawQuery) -> LawLookupResult:
        return LawLookupResult("not_found", ())


def ask(app) -> object:
    body = {"question": "상속 절차와 서류를 알려주세요", "requestId": "req-1"}
    return TestClient(app).post("/api/ai/ask", json=body)


def test_all_parts_answer(monkeypatch):
    monkeypatch.setattr(app_entry, "law_from_env", lambda: Law())
    app = app_entry.build_app(lambda: lambda purpose: FakeModel(), lambda: Search())
    response = ask(app)
    assert response.status_code == 200 and '"state": "answered"' in response.text


@pytest.mark.parametrize("missing", ["model", "search", "law"])
def test_any_missing_part_is_503(monkeypatch, missing):
    monkeypatch.setattr(app_entry, "law_from_env", lambda: None if missing == "law" else Law())
    model = (lambda: None) if missing == "model" else (lambda: lambda purpose: FakeModel())
    search = (lambda: None) if missing == "search" else (lambda: Search())
    assert ask(app_entry.build_app(model, search)).status_code == 503


def test_model_factory_rejects_bad_settings(monkeypatch):
    monkeypatch.setenv("LLM_AUTO_FALLBACK", "true")
    assert app_entry.model_factory_from_env() is None


# ---- 운영 lifespan(#111)의 RAG 초기화 실패 → A08 503 (수빈 님 확인 요청 항목) ------------------

RAG_ENV = {
    "DATABASE_URL": (
        "postgresql+asyncpg://postgres.abcdefghijklmnopqrst:secret-pw"
        "@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
    ),
    "RAG_DB_SCHEMA": "rag",
    "RAG_VECTOR_TABLE": "chunks",
    "RAG_COLLECTION_ID": "published-guides",
}


def _ask_through_lifespan() -> object:
    body = {"question": "상속 절차와 서류를 알려주세요", "requestId": "req-1"}
    with TestClient(app_entry.app) as client:  # with: lifespan(RAG 초기화)을 실제로 돈다.
        return client.post("/api/ai/ask", json=body)


@pytest.fixture
def ready_parts(monkeypatch):
    for name, value in RAG_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(app_entry, "model_factory_from_env", lambda: lambda purpose: FakeModel())
    monkeypatch.setattr(app_entry, "law_from_env", lambda: Law())


def test_lifespan_search_init_failure_is_503(ready_parts, monkeypatch, caplog):
    async def broken(**kwargs):
        raise OSError("connect to secret-pw failed")

    monkeypatch.setattr(app_entry, "create_postgres_search_port", broken)
    response = _ask_through_lifespan()
    assert response.status_code == 503
    assert response.json()["code"] == "PROVIDER_UNAVAILABLE"
    assert "secret-pw" not in caplog.text and "secret-pw" not in response.text


def test_lifespan_without_collection_id_is_503(ready_parts, monkeypatch):
    monkeypatch.setenv("RAG_COLLECTION_ID", "")
    assert _ask_through_lifespan().status_code == 503


def test_lifespan_with_ready_search_answers(ready_parts, monkeypatch):
    async def ready(**kwargs):
        return Search()

    monkeypatch.setattr(app_entry, "create_postgres_search_port", ready)
    response = _ask_through_lifespan()
    assert response.status_code == 200 and '"state": "answered"' in response.text
