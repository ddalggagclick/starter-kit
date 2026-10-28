# 담당: [B] | 책임: LawPort의 법령 근거 조회를 조립한다.
# PRD: E6 / 스토리 6-3 / 태스크 6-3-3; 상태 연계 E3 / 스토리 3-5 / 태스크 3-5-3.
# 구현할 기능: MCP 조문과 관련 부칙 전문을 0~N건의 LawLookupResult로 제공한다.
# 완료 기준: 누락·불일치 근거는 판단 유보에 전달하고 기술 장애는 별도 오류로 전달한다.
# 제한사항: 근거 부족은 S7, 기술 오류는 S6이다. PRD와 I06의 후보 탐색 범위가 달라 승인 전 확정하지 않는다.
# 상태: PRD 태스크 미시작.
"""LawPort.lookup 조립 (I11). MCP 조문 → (필요할 때) 같은 시행본의 OPEN API 부칙 전문 → 0~N건.

- 조문 0건이면 부칙 조회를 시작하지 않는다 (6-3-1).
- 부칙은 MCP가 실제로 돌려준 조문의 MST(시행본 고유 번호)로만 조회한다. 다른 개정 법률 후보를 찾지 않는다 (6-3-2).
- 조문이 불완전하거나, 부칙이 없거나, 부칙 시행본이 조문과 다르면 하나라도 전체를 ambiguous(S7)로 둔다.
- MCP·OPEN API 장애·시간 초과는 unavailable(S6)이다. verified가 아니면 근거를 내보내지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from inheritance.contracts.law import LawEvidence, LawLookupResult, LawQuery
from inheritance.law.addenda_contract import AddendumOpenApiPort, AmendmentCandidate
from inheritance.law.mcp_client import LawMcpPort, LawSourceUnavailable, McpArticle
from inheritance.law.open_api import AddendumNotFound

ADDENDUM_LOCATION = "부칙 전문"


class _Unverified(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LawLookupService:
    def __init__(
        self,
        mcp: LawMcpPort,
        addenda: AddendumOpenApiPort,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._mcp = mcp
        self._addenda = addenda
        self._clock = clock

    async def lookup(self, query: LawQuery) -> LawLookupResult:
        try:
            articles = await self._mcp.fetch_articles(query)
            if not articles:
                return LawLookupResult("not_found", ())
            checked_at = self._clock()
            evidence = [_article_evidence(article, checked_at) for article in articles]
            if query.needs_addenda:
                evidence.extend(await self._addenda_for(articles, query, checked_at))
        except LawSourceUnavailable:
            return LawLookupResult("unavailable", ())
        except _Unverified:
            return LawLookupResult("ambiguous", ())
        return LawLookupResult("verified", tuple(evidence))

    # 같은 시행본(MST)의 부칙은 한 번만 조회한다. MCP 발췌(addendum_excerpt)는 쓰지 않는다.
    async def _addenda_for(
        self, articles: tuple[McpArticle, ...], query: LawQuery, checked_at: str
    ) -> list[LawEvidence]:
        found: dict[str, LawEvidence] = {}
        for article in articles:
            if not article.mst:
                raise _Unverified  # 시행본을 식별할 수 없으면 추측하지 않는다 (3-3-3).
            if article.mst in found:
                continue
            candidate = AmendmentCandidate(
                law_id=article.law_id,
                mst=article.mst,
                promulgation_number=article.promulgation_number,
                effective_from=article.effective_from,
                reference_date=query.applicable_date,
            )
            try:
                full = await self._addenda.fetch_full_addendum(candidate)
            except AddendumNotFound:
                raise _Unverified from None
            got = full.candidate
            # 부칙 시행본이 조문과 다르면 미확인. MCP가 공포번호를 줬다면 그것도 맞아야 한다.
            if got.mst != article.mst or (
                article.promulgation_number
                and got.promulgation_number != article.promulgation_number
            ):
                raise _Unverified
            found[article.mst] = _evidence(
                evidence_id=f"law:{article.mst}:addendum",
                kind="addendum",
                law_title=article.law_title,
                article_number=ADDENDUM_LOCATION,
                article_text=full.full_text,
                effective_from=got.effective_from,
                official_url=full.official_url,
                checked_at=checked_at,
                law_id=article.law_id,
                mst=got.mst,
                promulgation_number=got.promulgation_number,
            )
        return list(found.values())


def _article_evidence(article: McpArticle, checked_at: str) -> LawEvidence:
    version = article.mst or article.law_id or article.effective_from
    return _evidence(
        evidence_id=f"law:{version}:{article.article_number}",
        kind="article",
        law_title=article.law_title,
        article_number=article.article_number,
        article_text=article.article_text,
        effective_from=article.effective_from,
        official_url=article.official_url,
        checked_at=checked_at,
        law_id=article.law_id,
        mst=article.mst,
        promulgation_number=article.promulgation_number,
    )


# LawEvidence 검증(빈 값, https가 아닌 URL, 부칙 식별값 없음)에 걸리면 미확인으로 처리한다.
def _evidence(**fields: object) -> LawEvidence:
    try:
        return LawEvidence(**fields)
    except ValueError:
        raise _Unverified from None
