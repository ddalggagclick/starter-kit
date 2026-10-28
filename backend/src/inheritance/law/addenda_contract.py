# 담당: [B] | 책임: 기존 MCP 조문·연혁과 공식 OPEN API 부칙 전문을 잇는 내부 후보 계약
# 구현할 기능: MST/공포번호/시행일 식별값, 전문 조회 및 같은 시행본 정합성 확인
# 코드 경계: 후보 선별 자동화는 필요한 때 조건부 구현. MCP 축약 발췌는 전문으로 인정 금지.
# 완료 기준: 보고서 ADD-01/ADD-02 15/15 원문 핵심구간·개정번호 회귀 시험.
"""정보 저장소 2026-10-14 B안. 후보 자동 추출은 조건부, 필수 E2E로 오인 금지."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AmendmentCandidate:
    law_id: str | None
    mst: str
    promulgation_number: str
    effective_from: str
    reference_date: str | None = None

    def __post_init__(self) -> None:
        if not self.mst or not self.promulgation_number or not self.effective_from:
            raise ValueError("amendment candidate requires version metadata")


@dataclass(frozen=True)
class FullAddendum:
    candidate: AmendmentCandidate
    full_text: str
    official_url: str

    def __post_init__(self) -> None:
        if not self.full_text.strip() or not self.official_url.startswith("https://"):
            raise ValueError("official complete addendum and URL required")


class AddendumOpenApiPort(Protocol):
    # AmendmentCandidate를 OPEN API 조회 조건으로 사용해 부칙 전문과 출처 HTTPS URL을 반환한다.
    async def fetch_full_addendum(self, candidate: AmendmentCandidate) -> FullAddendum: ...
