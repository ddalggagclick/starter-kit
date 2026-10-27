# 담당: [B] 제안 · 배치 승인: [통합] | 책임: V1 모의 검색·분류·답변 흐름 시험.
# PRD: 3-1-3, 3-3-4, 3-4-1, 3-4-2, 3-5-3, 3-6-4.
# 구현할 기능: 가짜 분류·검색·법령·모델로 생성 횟수, 출처 검증, S6/S7/S9 연결을 확인.
# 완료 기준: 진짜 LLM·RAG·법령 API를 호출하지 않고 통과.
"""V1ChatAnswerService 흐름 시험. 외부 서비스와 HTTP를 호출하지 않는다."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest
from inheritance.chat.safety import classify_model_error
from inheritance.chat.services.answer import V1ChatAnswerService
from inheritance.chat.services.citation_validation import extract_cited_ids
from inheritance.chat.services.prompt_builder import AnswerPromptBuilder
from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.contracts.routing import RouteDecision
from inheritance.core.errors import ErrorCode
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationChunk, GenerationRequest, GenerationResult
from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef

QUESTION = "상속포기는 언제까지 해야 하나요?"

RAG = Evidence(
    evidence_id="rag-1",
    source=SourceRef(
        source_id="guide-1",
        title="상속포기 안내",
        url="https://www.example.go.kr/guide",
        publisher="시험 기관",
        version="2026-10",
    ),
    text="상속포기 신고 방법 안내",
    location="2쪽",
)
ARTICLE = LawEvidence(
    evidence_id="law-1",
    kind="article",
    law_title="민법",
    article_number="제1019조",
    article_text="시험용 조문",
    effective_from="2026-01-01",
    official_url="https://www.law.go.kr/test-article",
    checked_at="2026-10-21",
)
ADDENDUM = LawEvidence(
    evidence_id="law-2",
    kind="addendum",
    law_title="민법",
    article_number="부칙 제1조",
    article_text="시험용 부칙",
    effective_from="2026-01-01",
    official_url="https://www.law.go.kr/test-addendum",
    checked_at="2026-10-21",
    mst="000001",
)


class FakeRouter:
    def __init__(self, decision: RouteDecision | None = None, error: Exception | None = None):
        self.decision = decision or RouteDecision("BOTH")
        self.error = error
        self.calls = 0

    async def classify(self, question: str) -> RouteDecision:
        self.calls += 1
        if self.error:
            raise self.error
        return self.decision


class FakeSearch:
    def __init__(self, evidence: tuple[Evidence, ...] = (), error: Exception | None = None):
        self.evidence = evidence
        self.error = error
        self.calls = 0

    async def search(self, request: SearchRequest) -> SearchResult:
        self.calls += 1
        if self.error:
            raise self.error
        return SearchResult(self.evidence)


class FakeLaw:
    def __init__(self, result: LawLookupResult | None = None):
        self.result = result or LawLookupResult("not_found", ())
        self.calls = 0

    async def lookup(self, query: LawQuery) -> LawLookupResult:
        self.calls += 1
        return self.result


class FakeModel:
    def __init__(self, text: str = "", error: ModelError | None = None):
        self.text = text
        self.error = error
        self.generate_calls = 0
        self.stream_calls = 0
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.generate_calls += 1
        return GenerationResult(self.text, "gemini", "fake")

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]:
        self.stream_calls += 1
        self.requests.append(request)

        async def chunks() -> AsyncIterator[GenerationChunk]:
            if self.error:
                raise self.error
            half = len(self.text) // 2
            yield GenerationChunk(self.text[:half])
            yield GenerationChunk(self.text[half:], done=True)

        return chunks()


def build(router=None, search=None, law=None, model=None):
    parts = (
        router or FakeRouter(),
        search or FakeSearch((RAG,)),
        law or FakeLaw(LawLookupResult("verified", (ARTICLE,))),
        model or FakeModel("상속포기 신고 방법은 안내를 확인하세요[[rag-1]]."),
    )
    return V1ChatAnswerService(*parts), parts


def ask(service, question=QUESTION, previous=()):
    return asyncio.run(service.answer(question, "req-1", previous))


def test_zero_evidence_means_no_generation_and_s7():
    service, (_, _, _, model) = build(search=FakeSearch(()), law=FakeLaw())
    result = ask(service)
    assert result.outcome.status == "abstained"
    assert result.outcome.answer_text is None
    assert result.error_code is None
    assert model.stream_calls == 0 and model.generate_calls == 0


def test_evidence_found_streams_exactly_once_and_returns_verified_references():
    text = "신고 방법은 안내를 확인하세요[[rag-1]]. 기간은 조문을 보세요[[law-1]]."
    service, (router, _, _, model) = build(model=FakeModel(text))
    result = ask(service)
    assert router.calls == 1
    assert model.stream_calls == 1 and model.generate_calls == 0
    assert model.requests[0].model_profile == "answer"
    assert result.outcome.status == "answered"
    # 내부 근거 ID는 출처 목록 순서의 번호로 바뀌어 나간다.
    assert (
        result.outcome.answer_text == "신고 방법은 안내를 확인하세요[1]. 기간은 조문을 보세요[2]."
    )
    refs = result.outcome.references
    assert [(r.evidence_id, r.kind) for r in refs] == [
        ("rag-1", "procedure"),
        ("law-1", "law_article"),
    ]
    assert refs[0].official_url == "https://www.example.go.kr/guide"
    assert refs[1].location == "제1019조"


def test_repeated_citation_keeps_its_first_number():
    text = "조문을 먼저 보세요[[law-1]]. 안내도 있습니다[[rag-1]]. 다시 조문입니다[[law-1]]."
    service, _ = build(model=FakeModel(text))
    result = ask(service)
    assert (
        result.outcome.answer_text
        == "조문을 먼저 보세요[1]. 안내도 있습니다[2]. 다시 조문입니다[1]."
    )
    assert [r.evidence_id for r in result.outcome.references] == ["law-1", "rag-1"]


@pytest.mark.parametrize(
    "text",
    [
        "근거에 없는 ID를 인용합니다[[made-up-9]].",
        "하나는 맞지만[[rag-1]] 하나는 틀립니다[[made-up-9]].",
        "인용이 하나도 없는 답변입니다.",
        "",
    ],
)
def test_unverified_or_missing_citation_is_s7(text):
    service, (_, _, _, model) = build(model=FakeModel(text))
    result = ask(service)
    assert model.stream_calls == 1
    assert result.outcome.status == "abstained"
    assert result.outcome.answer_text is None and result.outcome.references == ()


def test_prompt_separates_rag_article_and_addendum():
    messages = AnswerPromptBuilder().build(QUESTION, (RAG,), (ARTICLE, ADDENDUM), ("이전 질문",))
    assert [m.role for m in messages] == ["system", "user"]
    assert "[[근거ID]]" in messages[0].content
    user = messages[1].content
    order = ["[이전 질문]", "[안내자료]", "[법령 조문]", "[법령 부칙]", "[질문]"]
    positions = [user.index(title) for title in order]
    assert positions == sorted(positions)
    rag_part = user[user.index("[안내자료]") : user.index("[법령 조문]")]
    article_part = user[user.index("[법령 조문]") : user.index("[법령 부칙]")]
    addendum_part = user[user.index("[법령 부칙]") : user.index("[질문]")]
    assert "[[rag-1]]" in rag_part and "https://www.example.go.kr/guide" in rag_part
    assert "[[law-1]]" in article_part and "[[law-2]]" not in article_part
    assert "[[law-2]]" in addendum_part


def test_prompt_omits_empty_sections():
    user = AnswerPromptBuilder().build(QUESTION, (RAG,), ())[1].content
    assert "[안내자료]" in user
    assert "[법령 조문]" not in user and "[법령 부칙]" not in user and "[이전 질문]" not in user


@pytest.mark.parametrize(
    ("question", "previous"),
    [
        ("가" * 201, ()),
        ("   ", ()),
        (QUESTION, ("1", "2", "3", "4")),
        (QUESTION, ("가" * 201,)),
    ],
)
def test_input_policy_rejects_without_truncation(question, previous):
    service, (router, _, _, model) = build()
    with pytest.raises(ValueError):
        ask(service, question, previous)
    assert router.calls == 0 and model.stream_calls == 0


def test_input_policy_accepts_limits():
    service, (_, _, _, model) = build()
    assert ask(service, "가" * 200, ("1", "2", "3")).outcome.status == "answered"
    assert model.requests[0].messages[1].content.count("\n- ") == 3


@pytest.mark.parametrize(
    ("route", "search_calls", "law_calls"),
    [("RAG", 1, 0), ("LAW", 0, 1), ("BOTH", 1, 1)],
)
def test_route_selects_sources(route, search_calls, law_calls):
    search = FakeSearch((RAG,))
    law = FakeLaw(LawLookupResult("verified", (ARTICLE,)))
    text = "[[rag-1]]" if route == "RAG" else "[[law-1]]"
    service, _ = build(FakeRouter(RouteDecision(route)), search, law, FakeModel(f"답변{text}."))
    assert ask(service).outcome.status == "answered"
    assert (search.calls, law.calls) == (search_calls, law_calls)


def test_both_with_only_law_evidence_still_answers():
    service, _ = build(search=FakeSearch(()), model=FakeModel("조문을 보세요[[law-1]]."))
    assert ask(service).outcome.status == "answered"


def test_classification_invalid_output_continues_as_both():
    router = FakeRouter(error=ModelError(ModelErrorCode.INVALID_OUTPUT, "req-1"))
    search = FakeSearch((RAG,))
    law = FakeLaw(LawLookupResult("verified", (ARTICLE,)))
    service, _ = build(router, search, law)
    assert ask(service).outcome.status == "answered"
    assert (search.calls, law.calls) == (1, 1)


@pytest.mark.parametrize(
    ("code", "status", "error_code"),
    [
        (ModelErrorCode.RATE_LIMIT, "limited", ErrorCode.PROVIDER_RATE_LIMIT),
        (ModelErrorCode.TIMEOUT, "technical_error", ErrorCode.PROVIDER_TIMEOUT),
        (ModelErrorCode.UNAVAILABLE, "technical_error", ErrorCode.PROVIDER_UNAVAILABLE),
        (
            ModelErrorCode.UNSUPPORTED_CAPABILITY,
            "technical_error",
            ErrorCode.PROVIDER_UNAVAILABLE,
        ),
    ],
)
@pytest.mark.parametrize("stage", ["classify", "answer"])
def test_model_errors_map_to_s6_s9(code, status, error_code, stage):
    error = ModelError(code, "req-1")
    if stage == "classify":
        service, (_, _, _, model) = build(router=FakeRouter(error=error))
    else:
        service, (_, _, _, model) = build(model=FakeModel(error=error))
    result = ask(service)
    assert result.outcome.status == status
    assert result.error_code == error_code
    assert result.outcome.answer_text is None
    assert model.stream_calls == (1 if stage == "answer" else 0)


def test_answer_invalid_output_is_s7_without_regeneration():
    model = FakeModel(error=ModelError(ModelErrorCode.INVALID_OUTPUT, "req-1"))
    service, _ = build(model=model)
    result = ask(service)
    assert result.outcome.status == "abstained" and result.error_code is None
    assert model.stream_calls == 1


@pytest.mark.parametrize("stage", ["classify", "answer"])
def test_cancelled_request_returns_no_result(stage):
    error = ModelError(ModelErrorCode.CANCELLED, "req-1")
    if stage == "classify":
        service, _ = build(router=FakeRouter(error=error))
    else:
        service, _ = build(model=FakeModel(error=error))
    assert ask(service) is None


@pytest.mark.parametrize(
    ("search", "law"),
    [
        (FakeSearch(error=RuntimeError("down")), FakeLaw()),
        (FakeSearch((RAG,)), FakeLaw(LawLookupResult("unavailable", ()))),
    ],
)
def test_source_failure_is_s6_503(search, law):
    service, (_, _, _, model) = build(search=search, law=law)
    result = ask(service)
    assert result.outcome.status == "technical_error"
    assert result.error_code == ErrorCode.PROVIDER_UNAVAILABLE
    assert model.stream_calls == 0


def test_law_not_found_counts_as_zero_evidence():
    service, (_, _, _, model) = build(router=FakeRouter(RouteDecision("LAW")), law=FakeLaw())
    assert ask(service).outcome.status == "abstained"
    assert model.stream_calls == 0


def test_safety_http_status():
    assert classify_model_error(ModelErrorCode.RATE_LIMIT, "answer").http_status == 429
    assert classify_model_error(ModelErrorCode.TIMEOUT, "answer").http_status == 504
    assert classify_model_error(ModelErrorCode.UNAVAILABLE, "answer").http_status == 503
    assert classify_model_error(ModelErrorCode.INVALID_OUTPUT, "answer").http_status == 200


def test_extract_cited_ids_keeps_first_order_once():
    assert extract_cited_ids("a[[x]] b[[y]] c[[x]] d[[ bad ]]") == ("x", "y")


def test_question_text_is_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    service, _ = build()
    ask(service)
    assert QUESTION not in caplog.text
