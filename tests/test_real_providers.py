# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 실제 Gemini·법령 공급자 연동 시험(Fake 시험과 분리).
# PRD: 6-4-2 (Fake Port 계약 시험과 실제 Gemini/MCP/OPEN API 시험 분리 보고).
# 구현할 기능: 실제 분류(generate 1회)·답변(stream 1회)·출처 검증, 실제 법령 조문·부칙 조회를 확인한다.
# 완료 기준: RUN_REAL_PROVIDERS=1과 키가 있을 때만 실행. 없으면 건너뛴다(가상 응답을 실연동 성공으로 보고하지 않는다).
"""실제 외부 호출 시험. 비용·한도가 있으니 명시적으로 켤 때만 돈다.

실행 예: RUN_REAL_PROVIDERS=1 uv run --env-file .env pytest tests/test_real_providers.py -v
결과는 표본 확인일 뿐 전체 법률 안내 정확도를 보장하지 않는다.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from inheritance.chat.services.answer import V1ChatAnswerService
from inheritance.chat.services.question_router import ModelQuestionRouter
from inheritance.contracts.law import LawLookupResult, LawQuery
from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef

REAL = os.environ.get("RUN_REAL_PROVIDERS") == "1"


def _needs(*names: str):
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    return pytest.mark.skipif(
        not REAL or bool(missing),
        reason=f"실제 공급자 시험은 RUN_REAL_PROVIDERS=1과 {', '.join(names)}가 있을 때만 돈다",
    )


def _gemini_model(purpose: str):
    from starter_llm.providers.factory import create_model
    from starter_llm.runtime.settings import LLMSettings

    # 공급자 전환 없이 Gemini 자체를 확인한다(Groq 성공을 Gemini 성공으로 보고하지 않는다).
    settings = LLMSettings.from_env({**os.environ, "LLM_FAILOVER_PROVIDERS": "none"})
    return create_model(settings, purpose)


@_needs("GEMINI_API_KEY")
@pytest.mark.parametrize(
    ("question", "allowed"),
    [
        ("사망신고는 어디서 하나요?", {"RAG", "BOTH"}),
        ("민법 제1019조 상속 승인 기간 조문을 알려주세요", {"LAW", "BOTH"}),
    ],
)
def test_real_gemini_classifies_once(question, allowed):
    decision = asyncio.run(ModelQuestionRouter(_gemini_model("classifier")).classify(question))
    assert decision.route in allowed


RAG = Evidence(
    evidence_id="rag-death-report",
    source=SourceRef("guide-p01", "사망신고 안내", "https://www.gov.kr/", "정부24", "v1"),
    text="사망신고는 사망 사실을 안 날부터 1개월 이내에 시·구·읍·면·동에 할 수 있다.",
    location="1쪽",
)


class OneSearch:
    async def search(self, request: SearchRequest) -> SearchResult:
        return SearchResult((RAG,))


class NoLaw:
    async def lookup(self, query: LawQuery) -> LawLookupResult:
        return LawLookupResult("not_found", ())


@_needs("GEMINI_API_KEY")
def test_real_gemini_answer_is_verified_or_withheld():
    # 실제 답변이 근거 ID를 인용하면 answered, 아니면 판단 유보(S7). 기술 오류(S6)·한도(S9)면 실패로 본다.
    service = V1ChatAnswerService(
        ModelQuestionRouter(_gemini_model("classifier")),
        OneSearch(),
        NoLaw(),
        _gemini_model("answer"),
    )
    result = asyncio.run(service.answer("사망신고는 언제까지 해야 하나요?", "real-1"))
    assert result is not None and result.error_code is None
    assert result.outcome.status in ("answered", "abstained")
    if result.outcome.status == "answered":
        assert [r.evidence_id for r in result.outcome.references] == ["rag-death-report"]


@_needs("LAW_OC")
def test_real_law_article_and_addendum():
    from inheritance.law.mcp_client import KoreanLawMcp
    from inheritance.law.open_api import LawOpenApiAddenda
    from inheritance.law.service import LawLookupService

    service = LawLookupService(
        KoreanLawMcp(timeout_seconds=120), LawOpenApiAddenda(os.environ["LAW_OC"])
    )
    query = LawQuery(
        question="상속 승인 기간",
        law_names=("민법",),
        article_numbers=("제1019조",),
        needs_addenda=True,
    )
    result = asyncio.run(service.lookup(query))
    assert result.status == "verified"
    kinds = [e.kind for e in result.evidence]
    assert kinds == ["article", "addendum"]
    article = result.evidence[0]
    assert article.article_text.startswith("제1019조(")
    assert article.official_url.startswith("https://www.law.go.kr/")
    assert os.environ["LAW_OC"] not in article.official_url


@_needs("LAW_OC")
def test_real_law_unknown_article_is_not_found():
    from inheritance.law.mcp_client import KoreanLawMcp
    from inheritance.law.open_api import LawOpenApiAddenda
    from inheritance.law.service import LawLookupService

    service = LawLookupService(
        KoreanLawMcp(timeout_seconds=120), LawOpenApiAddenda(os.environ["LAW_OC"])
    )
    query = LawQuery(question="q", law_names=("민법",), article_numbers=("제9999조",))
    assert asyncio.run(service.lookup(query)).status == "not_found"
