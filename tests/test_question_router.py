# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 분류기와 V1 모의 흐름 시험.
# PRD: 3-2-1, 3-2-2, 3-2-5.
# 구현할 기능: 분류 JSON 변환, 형식 오류 처리, llm Fake ModelPort와의 통합 흐름을 확인.
# 완료 기준: 진짜 LLM·RAG·법령 API를 호출하지 않고 통과.
"""ModelQuestionRouter 단위 시험과 Fake ModelPort 통합 시험. 외부 서비스를 호출하지 않는다."""

from __future__ import annotations

import asyncio

import pytest
from inheritance.chat.services.answer import V1ChatAnswerService
from inheritance.chat.services.question_router import (
    CLASSIFIER_SYSTEM_PROMPT,
    ModelQuestionRouter,
    parse_route_decision,
)
from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.contracts.routing import QuestionRouterPort
from inheritance.core.errors import ErrorCode
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, GenerationResult
from starter_llm.providers.fake import FakeModel
from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef


class TextModel:
    """generate()가 정해진 텍스트를 돌려주는 시험용 모델."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[GenerationRequest] = []
        self.stream_calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        return GenerationResult(self.text, "gemini", "test")

    def stream(self, request: GenerationRequest):
        self.stream_calls += 1
        raise AssertionError("classifier must not stream")


def classify(text: str, question: str = "상속 절차가 궁금해요"):
    model = TextModel(text)
    decision = asyncio.run(ModelQuestionRouter(model).classify(question))
    return decision, model


# ---- 단위 시험 -------------------------------------------------------------


def test_router_satisfies_port_and_calls_generate_once_as_classifier():
    router: QuestionRouterPort = ModelQuestionRouter(TextModel('{"route": "RAG"}'))
    assert callable(router.classify)
    decision, model = classify('{"route": "RAG"}', "상속 절차가 궁금해요")
    assert decision.route == "RAG"
    assert len(model.requests) == 1 and model.stream_calls == 0
    request = model.requests[0]
    assert request.model_profile == "classifier"
    assert [m.role for m in request.messages] == ["system", "user"]
    assert request.messages[1].content == "상속 절차가 궁금해요"


def test_law_hints_are_passed_as_candidates():
    decision, _ = classify(
        '{"route": "LAW", "lawNames": ["민법", " "], "articleNumbers": ["제1019조"],'
        ' "referenceDate": "2022-12-13", "needsAddenda": true}'
    )
    assert decision.route == "LAW"
    assert decision.law_names == ("민법",)
    assert decision.article_numbers == ("제1019조",)
    assert decision.reference_date == "2022-12-13"
    assert decision.needs_addenda is True


@pytest.mark.parametrize(
    ("articles", "expected"),
    [
        ("[1019]", ("제1019조",)),
        ('["1019", " 제1020조 "]', ("제1019조", "제1020조")),
        ('["제1019조의2", 0, -1, true, 1.5, null, ""]', ("제1019조의2",)),
    ],
)
def test_numeric_article_numbers_become_article_strings(articles, expected):
    # 김선 님 실호출(민법 제1019조)에서 articleNumbers가 숫자로 와 빈 값이 되던 문제(#83).
    decision, _ = classify(
        f'{{"route": "LAW", "lawNames": ["민법"], "articleNumbers": {articles}}}'
    )
    assert decision.article_numbers == expected


def test_prompt_asks_article_numbers_as_strings():
    assert '"제1019조"' in CLASSIFIER_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "text",
    [
        '{"route": "BOTH", "lawNames": "민법", "articleNumbers": 1019, "referenceDate": "어제"}',
        '{"route": "BOTH", "needsAddenda": "yes"}',
    ],
)
def test_bad_hints_are_dropped_not_failed(text):
    decision, _ = classify(text)
    assert decision.route == "BOTH"
    assert (decision.law_names, decision.article_numbers, decision.reference_date) == ((), (), None)
    assert decision.needs_addenda is False


def test_code_fenced_json_is_accepted():
    decision, _ = classify('```json\n{"route": "LAW"}\n```')
    assert decision.route == "LAW"


@pytest.mark.parametrize(
    "text",
    ["분류 결과 아님", "", '["RAG"]', '{"route": "rag"}', '{"route": "NONE"}', '{"lawNames": []}'],
)
def test_invalid_output_raises_model_invalid_output(text):
    with pytest.raises(ModelError) as caught:
        parse_route_decision(text, "req-1")
    assert caught.value.code == ModelErrorCode.INVALID_OUTPUT


# ---- Fake ModelPort 통합 시험 (llm/starter_llm/providers/fake.py) -----------

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
    checked_at="2026-10-22",
)


class RecordingSearch:
    def __init__(self):
        self.requests: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> SearchResult:
        self.requests.append(request)
        return SearchResult((RAG,))


class RecordingLaw:
    def __init__(self):
        self.queries: list[LawQuery] = []

    async def lookup(self, query: LawQuery) -> LawLookupResult:
        self.queries.append(query)
        return LawLookupResult("verified", (ARTICLE,))


def run_flow(question: str):
    model, search, law = FakeModel(), RecordingSearch(), RecordingLaw()
    service = V1ChatAnswerService(ModelQuestionRouter(model), search, law, model)
    result = asyncio.run(service.answer(question, "req-1"))
    return result, model, search, law


@pytest.mark.parametrize(
    ("question", "searched", "looked_up"),
    [
        ("상속 절차와 서류를 알려주세요", 1, 0),
        ("민법 조문이 궁금해요", 0, 1),
        ("상속이 궁금해요", 1, 1),
    ],
)
def test_fake_flow_classifies_once_and_answers_once(question, searched, looked_up):
    result, model, search, law = run_flow(question)
    assert len(model.generated_requests) == 1
    assert model.generated_requests[0].model_profile == "classifier"
    assert len(model.streamed_requests) == 1
    assert model.streamed_requests[0].model_profile == "answer"
    assert (len(search.requests), len(law.queries)) == (searched, looked_up)
    # Fake는 user 메시지의 첫 [[근거ID]]를 인용한다(#69). 프롬프트는 [안내자료]가 [법령 조문]보다 앞이다.
    cited = "rag-1" if searched else "law-1"
    assert result.outcome.status == "answered" and result.error_code is None
    assert result.outcome.answer_text.endswith("[1]")
    assert [ref.evidence_id for ref in result.outcome.references] == [cited]


def test_fake_flow_without_evidence_skips_answer_generation():
    class EmptySearch:
        async def search(self, request: SearchRequest) -> SearchResult:
            return SearchResult(())

    class NotFoundLaw:
        async def lookup(self, query: LawQuery) -> LawLookupResult:
            return LawLookupResult("not_found", ())

    model = FakeModel()
    service = V1ChatAnswerService(ModelQuestionRouter(model), EmptySearch(), NotFoundLaw(), model)
    result = asyncio.run(service.answer("상속이 궁금해요", "req-1"))
    assert result.outcome.status == "abstained"
    assert len(model.generated_requests) == 1 and len(model.streamed_requests) == 0


def test_fake_flow_passes_law_hints_to_lookup():
    _, _, _, law = run_flow("민법 제1019조 부칙이 궁금해요")
    query = law.queries[0]
    assert query.law_names == ("민법",)
    assert query.article_numbers == ("제1019조",)
    assert query.needs_addenda is True


# FAKE_BAD_JSON은 분류만 깨지고 답변은 정상 → answered.
# FAKE_INVALID_OUTPUT은 답변 stream()도 같은 오류를 내므로 → 답변 단계 형식 오류 S7.
@pytest.mark.parametrize(
    ("marker", "status"), [("FAKE_BAD_JSON", "answered"), ("FAKE_INVALID_OUTPUT", "abstained")]
)
def test_fake_flow_bad_classification_continues_as_both(marker, status):
    result, model, search, law = run_flow(f"상속 절차 {marker}")
    assert (len(search.requests), len(law.queries)) == (1, 1)
    assert len(model.streamed_requests) == 1
    assert result.outcome.status == status and result.error_code is None


@pytest.mark.parametrize(
    ("marker", "status", "error_code"),
    [
        ("FAKE_RATE_LIMIT", "limited", ErrorCode.PROVIDER_RATE_LIMIT),
        ("FAKE_TIMEOUT", "technical_error", ErrorCode.PROVIDER_TIMEOUT),
        ("FAKE_UNAVAILABLE", "technical_error", ErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_fake_flow_model_errors_stop_before_search(marker, status, error_code):
    result, model, search, law = run_flow(f"상속 절차 {marker}")
    assert result.outcome.status == status
    assert result.error_code == error_code
    assert (len(search.requests), len(law.queries), len(model.streamed_requests)) == (0, 0, 0)
