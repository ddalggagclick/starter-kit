# 담당: [B] | 책임: 법제처 OPEN API로 관련 부칙 전문을 조회한다.
# PRD: E6 / 스토리 6-3 / 태스크 6-3-2.
# 구현할 기능: MCP가 반환한 조문 식별 정보에 연결된 부칙 전문과 공식 URL을 제공한다.
# 완료 기준: 해당 조문의 부칙 전문을 반환하고 시행본이 불일치하거나 조회되지 않으면 미확인으로 처리한다.
# 제한사항: MCP가 반환하지 않은 개정 법률 후보를 자동 탐색하지 않는다. 법령 원문을 RAG에 저장하지 않는다.
# 상태: PRD 태스크 미시작. API 상세는 공식 OPEN API 계약에 따라 구현한다.
"""법제처 OPEN API 부칙 전문 조회.

`lawService.do?target=law&MST=…&type=JSON`은 그 시행본의 기본정보(공포번호·시행일자)와 부칙 전체를 준다.
그중 기본정보의 공포번호와 같은 부칙(그 시행본 자신의 부칙)만 전문으로 돌려준다.
인증값은 `LAW_OC`(korean-law-mcp와 같은 이름)이다. 인증값이 담긴 요청 URL은 로그·오류에 남기지 않는다.
"""

from __future__ import annotations

from typing import Any

import httpx

from inheritance.law.addenda_contract import AddendumOpenApiPort, AmendmentCandidate, FullAddendum
from inheritance.law.mcp_client import LawSourceUnavailable, official_law_url

__all__ = [
    "AddendumNotFound",
    "AddendumOpenApiPort",
    "AmendmentCandidate",
    "FullAddendum",
    "LawOpenApiAddenda",
    "LawSourceUnavailable",
    "official_law_url",
]

LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
DEFAULT_TIMEOUT_SECONDS = 15.0


class AddendumNotFound(Exception):
    """요청한 시행본(MST·공포번호)의 부칙 전문이 없음. 장애가 아니라 미확인(S7)이다."""


class LawOpenApiAddenda:
    def __init__(
        self,
        oc: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not oc.strip():
            raise ValueError("LAW_OC is required")
        self._oc = oc
        self._client = client
        self._timeout = timeout_seconds

    async def fetch_full_addendum(self, candidate: AmendmentCandidate) -> FullAddendum:
        law = await self._law(candidate.mst)
        info = law.get("기본정보") or {}
        promulgation_number = _text(info.get("공포번호"))
        effective_from = _iso_date(_text(info.get("시행일자")))
        if not promulgation_number or not effective_from:
            raise AddendumNotFound
        units = _as_list((law.get("부칙") or {}).get("부칙단위"))
        own = [u for u in units if _same_number(u.get("부칙공포번호"), promulgation_number)]
        full_text = "\n".join(line for unit in own for line in _lines(unit.get("부칙내용"))).strip()
        if not full_text:
            raise AddendumNotFound
        got = AmendmentCandidate(
            law_id=_text(info.get("법령ID")) or candidate.law_id,
            mst=candidate.mst,
            promulgation_number=promulgation_number,
            effective_from=effective_from,
            reference_date=candidate.reference_date,
        )
        return FullAddendum(got, full_text, official_law_url(candidate.mst))

    # 네트워크 오류·시간 초과·JSON이 아닌 응답(점검·차단 페이지)은 장애(S6)로 본다. 원인 문구는 버린다.
    async def _law(self, mst: str) -> dict[str, Any]:
        params = {"OC": self._oc, "target": "law", "MST": mst, "type": "JSON"}
        try:
            if self._client is not None:
                response = await self._client.get(LAW_SERVICE_URL, params=params)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(LAW_SERVICE_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise LawSourceUnavailable from None
        law = data.get("법령") if isinstance(data, dict) else None
        if not isinstance(law, dict):
            raise AddendumNotFound
        return law


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _same_number(value: object, expected: str) -> bool:
    raw = _text(value)
    return raw.isdigit() and expected.isdigit() and int(raw) == int(expected)


def _iso_date(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 and raw.isdigit() else ""


def _as_list(value: object) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value] if value else []
    return [item for item in items if isinstance(item, dict)]


# 부칙내용은 문자열이거나 중첩 배열이다. 순서를 지켜 줄 단위로 편다.
def _lines(value: object) -> list[str]:
    if isinstance(value, str):
        return [line.rstrip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [line for item in value for line in _lines(item)]
    return []
