# 담당: [B] | 책임: korean-law-mcp 조문·연혁 조회를 정규화한다.
# PRD: E6 / 스토리 6-3 / 태스크 6-3-1.
# 구현할 기능: MCP가 반환한 조문·연혁과 식별 정보를 LawPort 결과로 전달한다.
# 완료 기준: 공식 조문 링크와 조회 메타데이터를 보존하고 불완전한 결과를 미확인으로 처리한다.
# 제한사항: 법령 원문을 RAG에 색인하지 않는다. OPEN API 부칙 조회는 별도 어댑터가 담당한다.
# 상태: PRD 태스크 미시작.
"""korean-law-mcp 조문 조회 계약 (I11 법령 근거 중 조문 부분).

실제 MCP 연결(korean-law-mcp@4.15.7 실행 방식)은 정해지지 않아 여기서는 정규화된 모양과 Port만 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inheritance.contracts.law import LawQuery


class LawSourceUnavailable(Exception):
    """MCP·OPEN API 장애나 시간 초과. 근거 부족(S7)과 구분되는 기술 오류(S6)다."""


@dataclass(frozen=True)
class McpArticle:
    # MCP가 실제로 돌려준 조문 한 건. 빈 값은 그대로 두고 service에서 미확인으로 처리한다.
    law_title: str
    article_number: str
    article_text: str
    effective_from: str
    official_url: str
    law_id: str | None = None
    mst: str | None = None
    promulgation_number: str | None = None
    # MCP의 3문장/250자 부칙 발췌. 부칙 전문이 아니므로 근거로 내보내지 않는다.
    addendum_excerpt: str | None = None


class LawMcpPort(Protocol):
    # LawQuery의 법령명·조문·기준일(applicable_date)로 조문을 찾는다. 없으면 빈 튜플.
    # 장애·시간 초과는 LawSourceUnavailable로 알린다.
    async def fetch_articles(self, query: LawQuery) -> tuple[McpArticle, ...]: ...
