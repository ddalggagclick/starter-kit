# 담당: [B] | 책임: korean-law-mcp 조문·연혁 조회를 정규화한다.
# PRD: E6 / 스토리 6-3 / 태스크 6-3-1.
# 구현할 기능: MCP가 반환한 조문·연혁과 식별 정보를 LawPort 결과로 전달한다.
# 완료 기준: 공식 조문 링크와 조회 메타데이터를 보존하고 불완전한 결과를 미확인으로 처리한다.
# 제한사항: 법령 원문을 RAG에 색인하지 않는다. OPEN API 부칙 조회는 별도 어댑터가 담당한다.
# 상태: PRD 태스크 미시작.
"""korean-law-mcp 조문 조회 (I11 법령 근거 중 조문 부분).

실행(2026-10-23 결정): 백엔드가 `npx -y korean-law-mcp@4.15.7`을 stdio 자식 프로세스로 띄운다.
인증값은 `LAW_OC` 환경 변수로만 넘긴다. 도구: search_law(법령명 → 법령ID·MST·시행일),
get_law_text(MST·조문·기준일 → 본문). 결과는 사람이 읽는 텍스트라 정해진 줄 형식만 읽고,
형식이 다르거나 [NOT_FOUND]이면 그 조문을 돌려주지 않는다(추측 금지).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from inheritance.contracts.law import LawQuery

MCP_PACKAGE = "korean-law-mcp@4.15.7"
DEFAULT_TIMEOUT_SECONDS = 30.0


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


# 국가법령정보센터 공개 본문 주소. lsiSeq에 MST(시행본 고유 번호)를 넣는다. 인증값이 들어가지 않는다.
def official_law_url(mst: str) -> str:
    return f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={mst}"


# 도구 이름과 인자를 받아 (본문 텍스트, 오류 여부)를 돌려준다. 시험에서는 가짜로 바꾼다.
ToolCall = Callable[[str, dict], Awaitable[tuple[str, bool]]]
ToolSession = Callable[[], AbstractAsyncContextManager[ToolCall]]

_HIT = re.compile(
    r"^\d+\. (?P<name>.+?)(?P<status> \[현행\]| ⚠️\[연혁-과거버전\])?\n"
    r"\s+- 법령ID: (?P<law_id>\S+)\n\s+- MST: (?P<mst>\d+)\n"
    r"\s+- 공포일: (?P<prom>\d{8})(?: / 시행일: (?P<eff>\d{8}))?",
    re.MULTILINE,
)
_LAW_NAME = re.compile(r"^법령명: (?P<name>.+)$", re.MULTILINE)
_EFFECTIVE = re.compile(r"^시행일: (?P<date>\d{8})$", re.MULTILINE)
_NOT_FOUND = "[NOT_FOUND]"
_TRUNCATED = "[응답 크기 제한]"


@dataclass(frozen=True)
class _LawHit:
    name: str
    law_id: str
    mst: str


class KoreanLawMcp:
    """LawMcpPort 구현. 질문마다 MCP 프로세스를 띄우고 닫는다(V1 단순 구조)."""

    def __init__(
        self,
        session: ToolSession | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session or stdio_tool_session
        self._timeout = timeout_seconds

    # 법령명·조문 후보가 없으면 찾지 않는다(분류 힌트는 후보일 뿐, 3-2-2).
    async def fetch_articles(self, query: LawQuery) -> tuple[McpArticle, ...]:
        if not query.law_names or not query.article_numbers:
            return ()
        try:
            async with asyncio.timeout(self._timeout), self._session() as call:
                return await self._fetch(call, query)
        except LawSourceUnavailable:
            raise
        except Exception:  # noqa: BLE001 - 실행 실패·시간 초과·통신 오류는 모두 장애(S6). 원인 문구는 버린다.
            raise LawSourceUnavailable from None

    async def _fetch(self, call: ToolCall, query: LawQuery) -> tuple[McpArticle, ...]:
        articles: list[McpArticle] = []
        ef_yd = (query.applicable_date or "").replace("-", "") or None
        for law_name in query.law_names:
            text, is_error = await call("search_law", {"query": law_name})
            hit = None if is_error else _current_hit(text, law_name)
            if hit is None:
                continue
            for number in query.article_numbers:
                args = {"mst": hit.mst, "jo": number}
                if ef_yd:
                    args["efYd"] = ef_yd
                body, body_error = await call("get_law_text", args)
                article = None if body_error else _article(body, number, hit)
                if article is not None:
                    articles.append(article)
        return tuple(articles)


# 정확히 같은 이름의 현행 법령만 쓴다. 과거 버전(연혁)과 부분 일치는 쓰지 않는다.
def _current_hit(text: str, law_name: str) -> _LawHit | None:
    for match in _HIT.finditer(text):
        if match["name"].strip() == law_name and (match["status"] or "").strip() == "[현행]":
            return _LawHit(match["name"].strip(), match["law_id"], match["mst"])
    return None


def _article(text: str, number: str, hit: _LawHit) -> McpArticle | None:
    if _NOT_FOUND in text:
        return None
    name, effective = _LAW_NAME.search(text), _EFFECTIVE.search(text)
    _, _, body = text.partition("\n\n")
    if not (name and effective and body.strip()) or name["name"].strip() != hit.name:
        return None
    lines = body.split(_TRUNCATED, 1)[0].strip().splitlines()
    # 본문은 "제N조(제목)" 줄부터다. 앞의 목차 줄은 버린다. 요청한 조문이 없으면 쓰지 않는다.
    start = next((i for i, line in enumerate(lines) if line.startswith(f"{number}(")), None)
    if start is None:
        return None
    raw = effective["date"]
    return McpArticle(
        law_title=hit.name,
        article_number=number,
        article_text="\n".join(lines[start:]).strip(),
        effective_from=f"{raw[:4]}-{raw[4:6]}-{raw[6:]}",
        official_url=official_law_url(hit.mst),
        law_id=hit.law_id,
        mst=hit.mst,
    )


# 실제 stdio 연결. npx는 PATH에서 찾고, 자식 프로세스에는 실행에 필요한 값과 LAW_OC만 넘긴다.
@asynccontextmanager
async def stdio_tool_session() -> AsyncIterator[ToolCall]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    npx = shutil.which("npx")
    oc = os.environ.get("LAW_OC", "")
    if not npx or not oc:
        raise LawSourceUnavailable
    env = {"PATH": os.environ.get("PATH", ""), "LAW_OC": oc}
    for name in ("SYSTEMROOT", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME"):
        if name in os.environ:  # Node·npx가 Windows/Linux에서 시작·캐시하는 데 필요하다.
            env[name] = os.environ[name]
    params = StdioServerParameters(command=npx, args=["-y", MCP_PACKAGE], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(name: str, arguments: dict) -> tuple[str, bool]:
            result = await session.call_tool(name, arguments)
            text = "\n".join(getattr(item, "text", "") for item in result.content)
            return text, bool(result.isError)

        yield call
