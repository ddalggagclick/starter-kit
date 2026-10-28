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
from inheritance.auth.jwt import AccessTokenInvalid
from inheritance.chat import router as chat_router
from inheritance.chat.services.answer import V1ChatAnswerService
from inheritance.chat.services.question_router import ModelQuestionRouter
from inheritance.chat.usage_limit import (
    GuestDailyLimiter,
    MemberMinuteLimiter,
    member_limiter_from_env,
)
from inheritance.contracts.chat import AnswerReference
from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.core.dependencies import build_chat_service, law_from_env
from inheritance.law.service import LawLookupService
from inheritance.main import create_app
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationChunk
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
    assert result["answer"].endswith("[1]") and cited not in result["answer"]
    expected = {
        "rag-1": ("상속 절차 안내", RAG.source.url),
        "law-1": ("민법", ARTICLE.official_url),
    }
    title, url = expected[cited]
    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == url and title in result["sources"][0]["title"]
    assert result["remainingToday"] == 9 and result["reasonCode"] is None


def test_zero_evidence_is_withheld_without_writing():
    client = make_client(search=Search(()), law=Law("not_found"))
    items = events(ask(client, "상속이 궁금해요"))
    assert [name for name, _ in items] == ["status", "status", "result"]
    assert "writing" not in [data.get("stage") for _, data in items]
    assert items[-1][1] == {
        "state": "withheld",
        "answer": None,
        "sources": [],
        "remainingToday": 9,
        "reasonCode": "SOURCE_NOT_VERIFIED",
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


# ---- 조립(core/dependencies.build_chat_service) ------------------------------


def test_build_chat_service_needs_model_search_and_law():
    factory = lambda purpose: FakeModel()
    assert build_chat_service(None, Search(), Law()) is None
    assert build_chat_service(factory, None, Law()) is None
    assert build_chat_service(factory, Search(), None) is None
    assert build_chat_service(factory, Search(), Law()) is not None


def test_build_chat_service_without_model_key_is_none():
    def no_key(purpose):
        raise ModelError(ModelErrorCode.UNAVAILABLE, "init")

    assert build_chat_service(no_key, Search(), Law()) is None


def test_create_app_uses_assembled_service():
    purposes = []

    def factory(purpose):
        purposes.append(purpose)
        return FakeModel()

    service = build_chat_service(factory, Search(), Law())
    response = ask(TestClient(create_app(chat_service=service)), "상속 절차와 서류를 알려주세요")
    assert purposes == ["classifier", "answer"]
    assert events(response)[-1][1]["state"] == "answered"


def test_law_from_env_needs_law_oc(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    assert law_from_env() is None
    monkeypatch.setenv("LAW_OC", "test-oc")
    assert isinstance(law_from_env(), LawLookupService)


# ---- URL 없는 RAG 출처(전화번호·공식 사이트 안내, #96) ---------------------------------

NO_URL = Evidence(
    evidence_id="rag-phone",
    source=SourceRef("guide-2", "상속 상담 전화 안내", None, "시험 기관", "v1"),
    text="상속 상담 전화 안내",
    location="2쪽",
)


def test_cited_source_without_url_is_answered_with_null_url():
    # Fake는 user 메시지의 첫 [[ID]]를 인용한다. URL 없는 근거만 있으면 그 근거를 인용한다.
    client = make_client(search=Search((NO_URL,)), law=Law("not_found"))
    result = events(ask(client, "상속 절차와 서류를 알려주세요"))[-1][1]
    assert result["state"] == "answered"
    assert result["sources"] == [{"title": "상속 상담 전화 안내", "url": None}]


def test_uncited_source_without_url_does_not_break_answer():
    client = make_client(search=Search((RAG, NO_URL)), law=Law("not_found"))
    result = events(ask(client, "상속 절차와 서류를 알려주세요"))[-1][1]
    assert result["state"] == "answered"
    assert result["sources"] == [{"title": "상속 절차 안내", "url": RAG.source.url}]


def test_law_reference_still_requires_https_url():
    with pytest.raises(ValueError):
        AnswerReference("law-1", "law_article", "민법", None, "제1019조", "2026-03-17")
    with pytest.raises(ValueError):
        AnswerReference("rag-1", "procedure", "안내", "http://example.com", "1쪽", "v1")
    assert AnswerReference("rag-1", "procedure", "안내", None, "1쪽", "v1").official_url is None


# ---- 판단 유보 사유(reasonCode) -------------------------------------------------------


def test_citation_mismatch_reason():
    class WrongCitationModel(FakeModel):
        def stream(self, request):
            async def chunks():
                yield GenerationChunk("근거와 다른 인용 [[없는-ID]]")

            self.streamed_requests.append(request)
            return chunks()

    app = create_app()
    model = WrongCitationModel()
    service = V1ChatAnswerService(ModelQuestionRouter(model), Search(), Law(), model)
    app.dependency_overrides[chat_router.get_chat_service] = lambda: service
    result = events(ask(TestClient(app), "상속 절차와 서류를 알려주세요"))[-1][1]
    assert (result["state"], result["reasonCode"]) == ("withheld", "CITATION_MISMATCH")


def test_answer_format_error_reason_is_null():
    result = events(ask(make_client(), "상속 절차 FAKE_INVALID_OUTPUT"))[-1][1]
    assert (result["state"], result["reasonCode"]) == ("withheld", None)


def test_answered_reason_is_null():
    result = events(ask(make_client(), "상속 절차와 서류를 알려주세요"))[-1][1]
    assert (result["state"], result["reasonCode"]) == ("answered", None)


# ---- 비회원 하루 10회 제한(3-7-2, 3-7-3) -------------------------------------------


def test_guest_eleventh_question_is_rate_limited_before_stream():
    client = make_client()
    remaining = [events(ask(client, "상속 절차와 서류를 알려주세요"))[-1][1]["remainingToday"]]
    remaining += [
        events(ask(client, "상속 절차와 서류를 알려주세요"))[-1][1]["remainingToday"]
        for _ in range(9)
    ]
    assert remaining == [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    limited = ask(client, "상속 절차와 서류를 알려주세요")
    # Gemini 한도(PROVIDER_RATE_LIMIT)와 다른 코드다.
    assert limited.status_code == 429
    # message는 사유 구분 키(비회원 하루 한도).
    assert limited.json() == {"code": "RATE_LIMITED", "message": "GUEST_DAILY_LIMIT"}


class Member:
    def user_id_from_access(self, token):
        if token not in ("good", "other"):
            raise AccessTokenInvalid
        return f"user-{token}"


def member_ask(client, token="good"):
    return client.post(
        "/api/ai/ask",
        json={"question": "상속 절차와 서류를 알려주세요", "requestId": "req-1"},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_member_has_no_daily_limit_and_gets_null_remaining():
    client = make_client()
    client.app.state.auth_service = Member()
    client.app.state.member_limiter = MemberMinuteLimiter(limit=100)
    for _ in range(11):
        assert events(member_ask(client))[-1][1]["remainingToday"] is None
    # 틀린 토큰은 비회원으로 센다.
    wrong = client.post(
        "/api/ai/ask",
        json={"question": "상속 절차와 서류를 알려주세요", "requestId": "req-1"},
        headers={"Authorization": "Bearer bad"},
    )
    assert events(wrong)[-1][1]["remainingToday"] == 9


def test_limiter_resets_daily_and_never_keeps_raw_ip():
    day = ["2026-10-26"]
    limiter = GuestDailyLimiter(limit=2, today=lambda: day[0])
    assert [limiter.take("203.0.113.7") for _ in range(3)] == [1, 0, None]
    assert limiter.take("198.51.100.1") == 1
    assert "203.0.113.7" not in repr(vars(limiter))
    day[0] = "2026-10-27"
    assert limiter.take("203.0.113.7") == 1


def test_unavailable_service_does_not_spend_guest_quota():
    client = TestClient(create_app())
    for _ in range(12):
        assert (
            client.post(
                "/api/ai/ask", json={"question": "상속 절차", "requestId": "req-1"}
            ).status_code
            == 503
        )


# ---- 4-5-2: AI 질문·답변 원문은 PostgreSQL에 영구 저장하지 않는다 ---------------------------


def test_chat_code_has_no_database_access():
    import ast
    from pathlib import Path

    chat_root = Path(__file__).resolve().parents[1] / "backend" / "src" / "inheritance" / "chat"
    banned = ("sqlalchemy", "asyncpg", "psycopg", "inheritance.core.database", "alembic")
    found = []
    for source in chat_root.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            found += [f"{source.name}:{n}" for n in names if n.startswith(banned)]
    assert found == []


def _guest_remaining(client, forwarded: str) -> int:
    response = client.post(
        "/api/ai/ask",
        json={"question": "상속 절차와 서류를 알려주세요", "requestId": "req-1"},
        headers={"X-Forwarded-For": forwarded},
    )
    return events(response)[-1][1]["remainingToday"]


def test_proxy_header_ignored_unless_trusted(monkeypatch):
    # 설정이 없으면 X-Forwarded-For를 믿지 않는다(꾸민 헤더로 횟수를 우회할 수 없다).
    monkeypatch.delenv("GUEST_LIMIT_TRUST_PROXY", raising=False)
    client = make_client()
    assert _guest_remaining(client, "1.1.1.1") == 9
    assert _guest_remaining(client, "2.2.2.2") == 8


def test_trusted_proxy_uses_rightmost_forwarded_ip(monkeypatch):
    # Render: 프록시가 맨 오른쪽에 실제 접속 IP를 붙인다. 왼쪽(사용자가 꾸민 값)은 무시한다.
    monkeypatch.setenv("GUEST_LIMIT_TRUST_PROXY", "true")
    client = make_client()
    assert _guest_remaining(client, "9.9.9.9, 203.0.113.1") == 9
    assert _guest_remaining(client, "8.8.8.8, 203.0.113.1") == 8
    assert _guest_remaining(client, "203.0.113.2") == 9


def test_member_eleventh_question_in_a_minute_is_rate_limited():
    # 3-7-3: 회원 1분 10회는 비회원 하루 한도와 다른 사유 키로 알린다. 다른 회원은 따로 센다.
    client = make_client()
    client.app.state.auth_service = Member()
    for _ in range(10):
        assert member_ask(client).status_code == 200
    limited = member_ask(client)
    assert limited.status_code == 429
    assert limited.json() == {"code": "RATE_LIMITED", "message": "MEMBER_MINUTE_LIMIT"}
    assert member_ask(client, "other").status_code == 200


def test_member_limiter_window_slides():
    now = [0.0]
    limiter = MemberMinuteLimiter(limit=2, clock=lambda: now[0])
    assert [limiter.take("u"), limiter.take("u"), limiter.take("u")] == [True, True, False]
    now[0] = 60.0
    assert limiter.take("u") is True


def test_member_limit_from_env(monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "3")
    limiter = member_limiter_from_env()
    assert [limiter.take("u") for _ in range(4)] == [True, True, True, False]
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "abc")
    fallback = member_limiter_from_env()  # 잘못된 값이면 기본 10회
    assert sum(fallback.take("u") for _ in range(11)) == 10
