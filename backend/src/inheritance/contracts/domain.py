# 담당: [B] | 책임: [B] 체크리스트 기능 사이의 내부 DTO 계약. 구현할 기능: 입력 정규화/추천≤5/수정 후 rule_version.
# 구현할 기능: Port/DTO의 입력 불변식과 정상·오류 동작을 계약 테스트로 확인.
# 코드 경계: 외부 서비스 호출/HTTP wire 상세를 이 파일에 구현하지 않는다.
# 완료 기준: Python 3.13 표준 라이브러리 계약 테스트 통과.
"""[B] 체크리스트 기능 사이의 내부 DTO 계약. 구현할 기능: 입력 정규화/추천≤5/수정 후 rule_version.
입력: 3개 초기 답변 + 선택 위험 답변 / 출력: 카드 ID·추천 사유·버전.
경계: HTTP/Pydantic 스키마가 아니며 카카오·웹은 동일한 추천 함수를 호출한다.
완료: 카드 ID 중복과 추천 6개를 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Relationship = Literal["spouse", "descendant", "ascendant", "sibling", "other", "unknown"]
AnswerChoice = Literal["yes", "no", "unknown"]
RiskId = Literal["debt", "property_disposal", "self_application"]
ProcedureId = Literal["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"]


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
class RecommendedProcedure:
    procedure_id: ProcedureId
    reason_code: str
    priority: int

    def __post_init__(self):
        if self.procedure_id not in tuple(f"p{i:02d}" for i in range(1, 9)):
            raise ValueError("invalid procedure id")
        if not self.reason_code or self.priority < 0:
            raise ValueError("invalid recommendation metadata")


@dataclass(frozen=True)
class RecommendationResult:
    procedures: tuple[RecommendedProcedure, ...]
    rule_version: str

    def __post_init__(self):
        if (
            not self.rule_version
            or len(self.procedures) > 5
            or len({p.procedure_id for p in self.procedures}) != len(self.procedures)
        ):
            raise ValueError("invalid recommendation result")
