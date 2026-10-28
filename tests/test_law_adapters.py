# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 법령 MCP·OPEN API 어댑터 시험.
# PRD: 6-3-1, 6-3-2, 6-3-3.
# 구현할 기능: korean-law-mcp 텍스트 읽기, OPEN API 부칙 선택, 장애·미확인 구분, 조립 결과를 확인.
# 완료 기준: 실제 MCP·법제처 호출 없이 통과. 응답 모양은 2026-10-23 실호출 결과를 줄였다.
"""법령 어댑터 시험. 가짜 MCP 도구와 httpx MockTransport만 쓴다."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from inheritance.contracts.law import LawQuery
from inheritance.law.addenda_contract import AmendmentCandidate
from inheritance.law.mcp_client import KoreanLawMcp, LawSourceUnavailable
from inheritance.law.open_api import AddendumNotFound, LawOpenApiAddenda
from inheritance.law.service import LawLookupService

SEARCH = """'민법' 검색 결과 (정확매칭 1건):

1. 난민법 [현행]
   - 법령ID: 011873
   - MST: 270351
   - 공포일: 20250415 / 시행일: 20250415
   - 구분: 법률

2. 민법 ⚠️[연혁-과거버전]
   - 법령ID: 001706
   - MST: 270000
   - 공포일: 20240101 / 시행일: 20240101
   - 구분: 법률

3. 민법 [현행]
   - 법령ID: 001706
   - MST: 284415
   - 공포일: 20260317 / 시행일: 20260317
   - 구분: 법률
"""
ARTICLE = """법령명: 민법
공포일: 20260317
시행일: 20260317
ℹ️ 조회기준일 20261023 — 위 시행일 버전 본문.

제1019조 승인, 포기의 기간
제1019조(승인, 포기의 기간)
①상속인은 상속개시있음을 안 날로부터 3월내에 단순승인이나 한정승인 또는 포기를 할 수 있다.
②상속인은 제1항의 승인 또는 포기를 하기 전에 상속재산을 조사할 수 있다.
"""
NOT_FOUND = """법령명: 민법
시행일: 20260317

[NOT_FOUND] 조문 내용을 찾을 수 없습니다.
"""


def fake_session(responses: dict[str, tuple[str, bool]], calls: list | None = None):
    @asynccontextmanager
    async def session():
        async def call(name, arguments):
            if calls is not None:
                calls.append((name, arguments))
            return responses[name]

        yield call

    return session


def query(**overrides) -> LawQuery:
    fields = {"question": "q", "law_names": ("민법",), "article_numbers": ("제1019조",)}
    return LawQuery(**{**fields, **overrides})


def fetch(mcp: KoreanLawMcp, q: LawQuery):
    return asyncio.run(mcp.fetch_articles(q))


# ---- MCP 조문 --------------------------------------------------------------


def test_mcp_reads_current_law_and_article_only():
    calls: list = []
    mcp = KoreanLawMcp(
        fake_session({"search_law": (SEARCH, False), "get_law_text": (ARTICLE, False)}, calls)
    )
    (article,) = fetch(mcp, query(applicable_date="2026-10-23"))
    # 부분 일치(난민법)·연혁(MST 270000)이 아니라 현행 민법을 고른다.
    assert (article.law_title, article.mst, article.law_id) == ("민법", "284415", "001706")
    assert article.article_text.startswith("제1019조(승인, 포기의 기간)")
    assert "승인, 포기의 기간\n제1019조" not in article.article_text
    assert article.effective_from == "2026-03-17"
    assert article.official_url == "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=284415"
    assert article.promulgation_number is None
    assert calls[1] == ("get_law_text", {"mst": "284415", "jo": "제1019조", "efYd": "20261023"})


@pytest.mark.parametrize(
    "responses",
    [
        {"search_law": ("검색 결과 없음", False), "get_law_text": (ARTICLE, False)},
        {"search_law": (SEARCH, True), "get_law_text": (ARTICLE, False)},
        {"search_law": (SEARCH, False), "get_law_text": (NOT_FOUND, True)},
        {
            "search_law": (SEARCH, False),
            "get_law_text": (ARTICLE.replace("제1019조(", "제1020조("), False),
        },
        {
            "search_law": (SEARCH, False),
            "get_law_text": (ARTICLE.replace("법령명: 민법", "법령명: 상법"), False),
        },
    ],
)
def test_mcp_unclear_results_are_dropped_not_guessed(responses):
    assert fetch(KoreanLawMcp(fake_session(responses)), query()) == ()


def test_mcp_needs_law_and_article_hints():
    calls: list = []
    mcp = KoreanLawMcp(fake_session({}, calls))
    assert fetch(mcp, query(article_numbers=())) == ()
    assert fetch(mcp, query(law_names=())) == ()
    assert calls == []


def test_mcp_failure_and_timeout_are_unavailable():
    @asynccontextmanager
    async def broken():
        raise OSError("npx 실행 실패")
        yield

    with pytest.raises(LawSourceUnavailable):
        fetch(KoreanLawMcp(broken), query())

    @asynccontextmanager
    async def slow():
        async def call(name, arguments):
            await asyncio.sleep(1)
            return SEARCH, False

        yield call

    with pytest.raises(LawSourceUnavailable):
        fetch(KoreanLawMcp(slow, timeout_seconds=0.01), query())


# ---- OPEN API 부칙 -----------------------------------------------------------

LAW_JSON = {
    "법령": {
        "기본정보": {"법령ID": "001706", "공포번호": "21454", "시행일자": "20260317"},
        "부칙": {
            "부칙단위": [
                {
                    "부칙공포번호": "19069",
                    "부칙내용": [["부칙 <제19069호,2022.12.13>"], ["옛 부칙"]],
                },
                {
                    "부칙공포번호": "21454",
                    "부칙내용": [
                        ["부칙 <제21454호,2026.3.17>"],
                        ["제1조(시행일) 이 법은 공포한 날부터 시행한다."],
                    ],
                },
            ]
        },
    }
}
CANDIDATE = AmendmentCandidate(None, "284415", None, "2026-03-17")


def addenda(handler) -> LawOpenApiAddenda:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LawOpenApiAddenda("test-oc", client)


def test_open_api_returns_own_addendum_of_that_version():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=LAW_JSON)

    full = asyncio.run(addenda(handler).fetch_full_addendum(CANDIDATE))
    assert seen["MST"] == "284415" and seen["target"] == "law" and seen["type"] == "JSON"
    assert full.candidate.promulgation_number == "21454"
    assert full.candidate.effective_from == "2026-03-17" and full.candidate.law_id == "001706"
    assert full.full_text.startswith("부칙 <제21454호,2026.3.17>")
    assert "옛 부칙" not in full.full_text
    assert full.official_url == "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=284415"
    assert "test-oc" not in full.official_url


@pytest.mark.parametrize(
    "body",
    [
        {"법령": {"기본정보": {"공포번호": "21454", "시행일자": "20260317"}, "부칙": {}}},
        {"법령": {"기본정보": {"시행일자": "20260317"}, "부칙": LAW_JSON["법령"]["부칙"]}},
        {"Law": "일치하는 법령이 없습니다."},
    ],
)
def test_open_api_missing_addendum_is_not_found(body):
    with pytest.raises(AddendumNotFound):
        asyncio.run(
            addenda(lambda r: httpx.Response(200, json=body)).fetch_full_addendum(CANDIDATE)
        )


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, text="<html>점검 중</html>")],
)
def test_open_api_errors_are_unavailable(response):
    with pytest.raises(LawSourceUnavailable):
        asyncio.run(addenda(lambda r: response).fetch_full_addendum(CANDIDATE))


def test_open_api_requires_oc():
    with pytest.raises(ValueError):
        LawOpenApiAddenda(" ")


# ---- 조립: MCP 조문(공포번호 없음) + OPEN API 부칙 ------------------------------


def test_lookup_joins_article_and_addendum_by_mst():
    mcp = KoreanLawMcp(
        fake_session({"search_law": (SEARCH, False), "get_law_text": (ARTICLE, False)})
    )
    service = LawLookupService(
        mcp, addenda(lambda r: httpx.Response(200, json=LAW_JSON)), clock=lambda: "2026-10-23"
    )
    result = asyncio.run(service.lookup(query(needs_addenda=True)))
    assert result.status == "verified"
    assert [e.kind for e in result.evidence] == ["article", "addendum"]
    addendum = result.evidence[1]
    assert (addendum.mst, addendum.promulgation_number) == ("284415", "21454")
