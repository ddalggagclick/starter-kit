# 담당: [B] | 책임: MCP 조문·연혁과 법제처 OPEN API 부칙 전문 결과를 다건 공식 근거로 반환
# 구현할 기능: LawPort.lookup, 시행본 식별, 공식 원문 개별 링크, incomplete 부칙의 미검증 처리
# 코드 경계: 관련 부칙 자동 후보 선별은 필요 시 law/ 담당의 조건부 구현이며 벡터 DB에 법령을 저장하지 않는다.
# 완료 기준: MCP 조문 0~N, OPEN API 부칙 0~N, 과거 시행본/누락/불일치 Fake 계약 테스트 통과.
"""2026-10-14 information 법령 MCP 기술검증의 승인 B안을 보존한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

LawStatus = Literal["verified", "not_found", "unavailable", "ambiguous"]
LawEvidenceKind = Literal["article", "addendum"]


@dataclass(frozen=True)
class LawQuery:
    question: str
    applicable_date: str | None = None
    law_names: tuple[str, ...] = ()
    article_numbers: tuple[str, ...] = ()
    needs_addenda: bool = False

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("law question must not be empty")


@dataclass(frozen=True)
class LawEvidence:
    evidence_id: str
    kind: LawEvidenceKind
    law_title: str
    article_number: str  # 부칙이면 '부칙 제X조' 또는 '부칙 전문'
    article_text: str  # 공식 조문 또는 대상 부칙 전문; MCP 발췌를 부칙 전문으로 표시 금지
    effective_from: str
    official_url: str
    checked_at: str
    law_id: str | None = None
    mst: str | None = None
    promulgation_number: str | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.evidence_id,
                self.law_title,
                self.article_number,
                self.article_text,
                self.effective_from,
                self.official_url,
                self.checked_at,
            )
        ):
            raise ValueError("law evidence requires complete official citation metadata")
        if self.kind not in ("article", "addendum") or not self.official_url.startswith("https://"):
            raise ValueError("law evidence kind and official HTTPS URL required")
        if self.kind == "addendum" and not (self.mst or self.promulgation_number):
            raise ValueError("addendum needs amendment/version identifier")


@dataclass(frozen=True)
class LawLookupResult:
    status: LawStatus
    evidence: tuple[LawEvidence, ...]

    def __post_init__(self) -> None:
        if self.status == "verified" and not self.evidence:
            raise ValueError("verified law lookup requires at least one evidence")
        if self.status != "verified" and self.evidence:
            raise ValueError("unverified law lookup must not expose verified evidence")


class LawPort(Protocol):
    # 조회 상태를 구분하며 verified가 아닐 때는 검증된 evidence를 반환하지 않는다.
    async def lookup(self, query: LawQuery) -> LawLookupResult: ...
