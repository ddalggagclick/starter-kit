# 담당: [B] | 책임: 공통 체크리스트 안내의 내부 DTO 계약.
# 구현할 기능: 공통 안내 입력·결과 DTO의 검증 경계를 정의한다.
# 코드 경계: 외부 서비스와 HTTP wire 세부는 여기서 구현하지 않는다.
# 완료 기준: p01~p08 전체와 콘텐츠 버전을 표현한다.
"""공통 체크리스트 안내의 입력·결과 DTO 계약.

안내·위험 payload는 상세 구조 확정 전까지 내부 계약에서만 object로 둔다.
이 DTO는 최종 HTTP API 스키마가 아니며 절차 표시 순서를 정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Relationship = Literal["spouse", "descendant", "ascendant", "sibling", "other", "unknown"]
AnswerChoice = Literal["yes", "no", "unknown"]
RiskId = Literal["debt", "property_disposal", "self_application"]
ProcedureId = Literal["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"]
PROCEDURE_IDS = frozenset(("p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"))


@dataclass(frozen=True)
class InitialAnswers:
    relationship: Relationship
    death_date: str | None  # YYYY-MM-DD; 알 수 없으면 None
    death_date_unknown: bool
    one_stop_application: AnswerChoice

    def __post_init__(self):
        if self.relationship not in (
            "spouse",
            "descendant",
            "ascendant",
            "sibling",
            "other",
            "unknown",
        ):
            raise ValueError("invalid relationship choice")
        if self.one_stop_application not in ("yes", "no", "unknown"):
            raise ValueError("invalid one-stop answer")
        if self.death_date_unknown == (self.death_date is not None):
            raise ValueError("death date known/unknown mismatch")
        if self.death_date is not None:
            try:
                parsed_date = date.fromisoformat(self.death_date)
            except ValueError:
                raise ValueError("death date must use YYYY-MM-DD") from None
            if parsed_date.isoformat() != self.death_date:
                raise ValueError("death date must use YYYY-MM-DD")


@dataclass(frozen=True)
class RiskAnswer:
    risk_id: RiskId
    answer: AnswerChoice
    confirmed: bool = False

    def __post_init__(self):
        if self.risk_id not in (
            "debt",
            "property_disposal",
            "self_application",
        ) or self.answer not in ("yes", "no", "unknown"):
            raise ValueError("invalid risk answer")


@dataclass(frozen=True)
class ProcedureGuidance:
    procedure_id: ProcedureId

    def __post_init__(self):
        if self.procedure_id not in PROCEDURE_IDS:
            raise ValueError("invalid procedure id")


@dataclass(frozen=True)
class GuidanceResult:
    procedures: tuple[ProcedureGuidance, ...]
    guidance: object
    risk_information: object
    content_version: str

    def __post_init__(self):
        if not isinstance(self.content_version, str) or not self.content_version.strip():
            raise ValueError("content version must be a nonempty string")
        if not isinstance(self.procedures, tuple) or any(
            not isinstance(item, ProcedureGuidance) for item in self.procedures
        ):
            raise ValueError("procedures must contain procedure guidance")
        procedure_ids = tuple(procedure.procedure_id for procedure in self.procedures)
        if len(procedure_ids) != len(PROCEDURE_IDS) or set(procedure_ids) != PROCEDURE_IDS:
            raise ValueError("guidance result must contain each procedure exactly once")
