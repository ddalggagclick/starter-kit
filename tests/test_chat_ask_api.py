# 담당: [B] 제안 · 배치 승인: [통합] | 책임: A08 AI 질문 SSE API 계약 시험.
# PRD: 3-1-4, 3-5-2, 3-5-3 / openapi.yaml A08_askAi, SseEvents.
# 구현할 기능: status → result/error 순서, 출처 모양, 판단 유보, 오류 코드, 입력 검증, 연결 전 503을 확인.
# 완료 기준: 진짜 LLM·RAG·법령 API를 호출하지 않고 통과.
"""A08 SSE 시험. llm Fake ModelPort와 시험용 검색·법령 Port만 쓴다."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient
from inheritance.chat import router as chat_router
from inheritance.chat.services.answer import V1ChatAnswerService
from inheritance.chat.services.question_router import ModelQuestionRouter
from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.main import create_app
from starter_llm.providers.fake import FakeModel
from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef

RAG = Evidence(
    evidence_id="rag-1",
    source=SourceRef(
        "guide-1", "상속 절차 안내", "https://www.example.go.kr/guide", "시험 기관", "v1"
    ),
    text="상속 절차 안내",
    location="1쪽",
)
ARTICLE = LawEvidence(
    evidence_id="law-1",
    kind="article",
    law_title="민법",
    article_number="제1019조",
    article_text="시험용 조문",
    effective_from="2026-01-01",
    official_url="https://www.law.go.kr/test",
    checked_at="2026-10-23",
)


class Search:
    def __init__(self, evidence=(RAG,)):
        self.evidence = evidence

    async def search(self, request: SearchRequest) -> SearchResult:
        return SearchResult(self.evidence)


class Law:
    def __init__(self, status="verified"):
        self.status = status

    async def lookup(self, query: LawQuery) -> LawLookupResult:
        evidence = (ARTICLE,) if self.status == "verified" else ()
        return LawLookupResult(self.status, evidence)


def make_client(search=None, law=None) -> TestClient:
    app = create_app()
    model = FakeModel()
    service = V1ChatAnswerService(
        ModelQuestionRouter(model), search or Search(), law or Law(), model
    )
    app.dependency_overrides[chat_router.get_chat_service] = lambda: service
    return TestClient(app)


def ask(client: TestClient, question: str, **extra):
    body = {"question": question, "requestId": "req-1", **extra}
    return client.post("/api/ai/ask", json=body)


def events(response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        name, data = block.split("\n")
        parsed.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return parsed


@pytest.mark.parametrize(
    ("question", "stages", "cited"),
    [
        ("상속 절차와 서류를 알려주세요", ["searching", "writing"], "rag-1"),
        ("민법 조문이 궁금해요", ["lawChecking", "writing"], "law-1"),
        ("상속이 궁금해요", ["searching", "lawChecking", "writing"], "rag-1"),
    ],
)
def test_status_events_then_verified_answer(question, stages, cited):
    response = ask(make_client(), question)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    items = events(response)
    assert [name for name, _ in items] == ["status"] * len(stages) + ["result"]
    assert [data["stage"] for _, data in items[:-1]] == stages
    result = items[-1][1]
    assert result["state"] == "answered"
    assert result["answer"].endswith(f"[[{cited}]]")
    expected = {
        "rag-1": ("상속 절차 안내", RAG.source.url),
        "law-1": ("민법", ARTICLE.official_url),
    }
    title, url = expected[cited]
    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == url and title in result["sources"][0]["title"]
    assert result["remainingToday"] is None and result["reasonCode"] is None


def test_zero_evidence_is_withheld_without_writing():
    client = make_client(search=Search(()), law=Law("not_found"))
    items = events(ask(client, "상속이 궁금해요"))
    assert [name for name, _ in items] == ["status", "status", "result"]
    assert "writing" not in [data.get("stage") for _, data in items]
    assert items[-1][1] == {
        "state": "withheld",
        "answer": None,
        "sources": [],
        "remainingToday": None,
        "reasonCode": None,
    }


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        ("FAKE_RATE_LIMIT", "PROVIDER_RATE_LIMIT"),
        ("FAKE_TIMEOUT", "PROVIDER_TIMEOUT"),
        ("FAKE_UNAVAILABLE", "PROVIDER_UNAVAILABLE"),
    ],
)
def test_model_errors_become_one_error_event(marker, code):
    items = events(ask(make_client(), f"상속 절차 {marker}"))
    assert items == [("error", {"code": code, "message": code, "requestId": "req-1"})]


def test_law_source_unavailable_is_error_event():
    items = events(ask(make_client(law=Law("unavailable")), "민법 조문이 궁금해요"))
    assert items[-1] == (
        "error",
        {"code": "PROVIDER_UNAVAILABLE", "message": "PROVIDER_UNAVAILABLE", "requestId": "req-1"},
    )


def test_unexpected_error_hides_details():
    class BrokenService:
        async def answer(self, *args, **kwargs):
            raise RuntimeError("내부 상세 정보")

    app = create_app()
    app.dependency_overrides[chat_router.get_chat_service] = lambda: BrokenService()
    response = ask(TestClient(app), "상속 절차")
    assert "내부 상세 정보" not in response.text
    assert events(response)[-1][1]["code"] == "PROVIDER_UNAVAILABLE"


@pytest.mark.parametrize(
    "body",
    [
        {"question": "가" * 201, "requestId": "req-1"},
        {"question": "   ", "requestId": "req-1"},
        {"question": "상속", "requestId": ""},
        {"question": "상속"},
        {"question": "상속", "requestId": "req-1", "previousQuestions": ["a", "b", "c", "d"]},
        {"question": "상속", "requestId": "req-1", "previousQuestions": ["가" * 201]},
    ],
)
def test_invalid_input_is_422_before_stream(body):
    response = make_client().post("/api/ai/ask", json=body)
    assert response.status_code == 422
    assert response.json() == {"code": "VALIDATION_ERROR", "message": "VALIDATION_ERROR"}


def test_200_code_points_and_three_previous_questions_are_allowed():
    response = ask(make_client(), "가" * 200, previousQuestions=["a", "b", "c"])
    assert response.status_code == 200
    assert events(response)[-1][0] == "result"


def test_service_not_connected_is_503_before_stream():
    response = TestClient(create_app()).post(
        "/api/ai/ask", json={"question": "상속 절차", "requestId": "req-1"}
    )
    assert response.status_code == 503
    assert response.json() == {"code": "PROVIDER_UNAVAILABLE", "message": "PROVIDER_UNAVAILABLE"}


def test_question_and_answer_are_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    question = "어머니 빚이 3천만원인데 상속 절차가 궁금해요"
    response = ask(make_client(), question)
    answer = events(response)[-1][1]["answer"]
    assert question not in caplog.text and answer not in caplog.text
    record = next(r for r in caplog.records if getattr(r, "event", None) == "chat.ask")
    assert (record.status, record.trace_id, record.error_code) == ("answered", "req-1", None)


def test_closing_stream_cancels_service_and_sends_no_late_result():
    # 연결이 끊기면 Starlette가 스트림을 닫는다. 그때 진행 중인 서비스 작업이 취소돼야 한다(3-5-2).
    state = {"cancelled": False}

    class SlowService:
        async def answer(self, question, request_id, previous=(), progress=None):
            await progress("searching")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                state["cancelled"] = True
                raise

    async def scenario():
        stream = chat_router._events(SlowService(), "상속 절차", "req-1", ())
        first = await anext(stream)
        await stream.aclose()
        return first

    first = asyncio.run(scenario())
    assert first.startswith("event: status")
    assert state["cancelled"] is True
