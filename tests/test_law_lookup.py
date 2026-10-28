# 담당: [B] 제안 · 배치 승인: [통합] | 책임: 법령 MCP 조문·OPEN API 부칙 조립 시험.
# PRD: 6-3-1, 6-3-2, 6-3-3, 3-3-3.
# 구현할 기능: 가짜 MCP·OPEN API로 0~N건, 시행본 일치, 장애·미확인 구분을 확인.
# 완료 기준: 진짜 korean-law-mcp·법제처 API를 호출하지 않고 통과.
"""LawLookupService 시험. ADD-01·ADD-02 식별값은 10/14 B안 기술검증 회귀 기준을 따른다."""

from __future__ import annotations

import asyncio

import pytest
from inheritance.contracts.law import LawPort, LawQuery
from inheritance.law.addenda_contract import AmendmentCandidate, FullAddendum
from inheritance.law.mcp_client import LawSourceUnavailable, McpArticle
from inheritance.law.open_api import AddendumNotFound
from inheritance.law.service import LawLookupService

CHECKED = "2026-10-22T00:00:00+00:00"

# ADD-01: 민법 법률 제19069호 (MST 245913, 시행 2022-12-13)
CIVIL = McpArticle(
    law_title="민법",
    article_number="제1019조",
    article_text="시험용 조문 본문",
    effective_from="2022-12-13",
    official_url="https://www.law.go.kr/test-civil",
    law_id="001706",
    mst="245913",
    promulgation_number="19069",
    addendum_excerpt="MCP 발췌(전문 아님)",
)
CIVIL_OTHER_ARTICLE = McpArticle(
    law_title="민법",
    article_number="제1020조",
    article_text="시험용 조문 본문 2",
    effective_from="2022-12-13",
    official_url="https://www.law.go.kr/test-civil-2",
    law_id="001706",
    mst="245913",
    promulgation_number="19069",
)
# ADD-02: 상속세 및 증여세법 법률 제19195호 (MST 247439, 시행 2023-01-01)
TAX = McpArticle(
    law_title="상속세 및 증여세법",
    article_number="제67조",
    article_text="시험용 조문 본문 3",
    effective_from="2023-01-01",
    official_url="https://www.law.go.kr/test-tax",
    mst="247439",
    promulgation_number="19195",
)


def full_addendum(candidate: AmendmentCandidate, *, mst: str | None = None) -> FullAddendum:
    got = AmendmentCandidate(
        law_id=candidate.law_id,
        mst=mst or candidate.mst,
        promulgation_number=candidate.promulgation_number,
        effective_from=candidate.effective_from,
        reference_date=candidate.reference_date,
    )
    return FullAddendum(got, f"부칙 전문 {got.mst}", f"https://www.law.go.kr/addendum/{got.mst}")


class FakeMcp:
    def __init__(self, articles=(), error: Exception | None = None):
        self.articles = tuple(articles)
        self.error = error
        self.queries: list[LawQuery] = []

    async def fetch_articles(self, query: LawQuery):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.articles


class FakeOpenApi:
    def __init__(self, behavior=None):
        self.behavior = behavior or (lambda candidate: full_addendum(candidate))
        self.candidates: list[AmendmentCandidate] = []

    async def fetch_full_addendum(self, candidate: AmendmentCandidate) -> FullAddendum:
        self.candidates.append(candidate)
        return self.behavior(candidate)


def lookup(mcp, open_api=None, **query):
    open_api = open_api or FakeOpenApi()
    service = LawLookupService(mcp, open_api, clock=lambda: CHECKED)
    result = asyncio.run(service.lookup(LawQuery("상속포기 기간이 궁금해요", **query)))
    return result, open_api


def test_service_satisfies_law_port():
    port: LawPort = LawLookupService(FakeMcp(), FakeOpenApi())
    assert callable(port.lookup)


def test_zero_articles_is_not_found_without_open_api_call():
    result, open_api = lookup(FakeMcp(), needs_addenda=True)
    assert result.status == "not_found" and result.evidence == ()
    assert open_api.candidates == []


def test_articles_without_addenda_request_skip_open_api():
    result, open_api = lookup(FakeMcp([CIVIL, TAX]))
    assert result.status == "verified"
    assert open_api.candidates == []
    assert [(e.kind, e.law_title, e.article_number, e.official_url) for e in result.evidence] == [
        ("article", "민법", "제1019조", "https://www.law.go.kr/test-civil"),
        ("article", "상속세 및 증여세법", "제67조", "https://www.law.go.kr/test-tax"),
    ]
    assert all(e.checked_at == CHECKED for e in result.evidence)


def test_addenda_are_fetched_once_per_version_and_keep_add01_add02_identity():
    result, open_api = lookup(FakeMcp([CIVIL, CIVIL_OTHER_ARTICLE, TAX]), needs_addenda=True)
    assert result.status == "verified"
    # 같은 시행본(민법 245913)은 한 번만 조회, MCP가 돌려준 조문의 식별값으로만 조회한다.
    assert [(c.mst, c.promulgation_number) for c in open_api.candidates] == [
        ("245913", "19069"),
        ("247439", "19195"),
    ]
    addenda = [e for e in result.evidence if e.kind == "addendum"]
    assert [(e.mst, e.promulgation_number, e.effective_from) for e in addenda] == [
        ("245913", "19069", "2022-12-13"),
        ("247439", "19195", "2023-01-01"),
    ]
    assert all(e.article_number == "부칙 전문" for e in addenda)
    assert all(e.official_url.startswith("https://") for e in result.evidence)
    assert len(result.evidence) == 5
    assert len({e.evidence_id for e in result.evidence}) == 5


def test_mcp_excerpt_is_never_used_as_addendum():
    def not_found(candidate):
        raise AddendumNotFound

    result, _ = lookup(FakeMcp([CIVIL]), FakeOpenApi(not_found), needs_addenda=True)
    assert result.status == "ambiguous" and result.evidence == ()


def test_addendum_version_mismatch_is_ambiguous():
    result, _ = lookup(
        FakeMcp([CIVIL]),
        FakeOpenApi(lambda c: full_addendum(c, mst="999999")),
        needs_addenda=True,
    )
    assert result.status == "ambiguous" and result.evidence == ()


def test_article_without_version_identity_cannot_request_addendum():
    unknown = McpArticle("민법", "제1019조", "본문", "2022-12-13", "https://www.law.go.kr/x")
    result, open_api = lookup(FakeMcp([unknown]), needs_addenda=True)
    assert result.status == "ambiguous"
    assert open_api.candidates == []
    # 부칙이 필요 없으면 같은 조문도 근거로 쓸 수 있다.
    assert lookup(FakeMcp([unknown]))[0].status == "verified"


@pytest.mark.parametrize(
    "broken",
    [
        McpArticle("민법", "제1019조", "", "2022-12-13", "https://www.law.go.kr/x"),
        McpArticle("민법", "제1019조", "본문", "2022-12-13", "http://www.law.go.kr/x"),
        McpArticle("민법", "제1019조", "본문", "", "https://www.law.go.kr/x"),
    ],
)
def test_incomplete_article_is_ambiguous(broken):
    result, _ = lookup(FakeMcp([CIVIL, broken]))
    assert result.status == "ambiguous" and result.evidence == ()


def test_mcp_outage_is_unavailable_not_not_found():
    result, open_api = lookup(FakeMcp(error=LawSourceUnavailable()), needs_addenda=True)
    assert result.status == "unavailable" and result.evidence == ()
    assert open_api.candidates == []


def test_open_api_outage_is_unavailable():
    def down(candidate):
        raise LawSourceUnavailable

    result, _ = lookup(FakeMcp([CIVIL]), FakeOpenApi(down), needs_addenda=True)
    assert result.status == "unavailable" and result.evidence == ()


def test_reference_date_is_passed_to_mcp_and_addendum_candidate():
    mcp = FakeMcp([CIVIL])
    _, open_api = lookup(mcp, applicable_date="2022-12-31", needs_addenda=True)
    assert mcp.queries[0].applicable_date == "2022-12-31"
    assert open_api.candidates[0].reference_date == "2022-12-31"


def test_law_hints_are_passed_to_mcp_query():
    mcp = FakeMcp([CIVIL])
    lookup(mcp, law_names=("민법",), article_numbers=("제1019조",))
    assert mcp.queries[0].law_names == ("민법",)
    assert mcp.queries[0].article_numbers == ("제1019조",)
