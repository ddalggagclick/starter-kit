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
