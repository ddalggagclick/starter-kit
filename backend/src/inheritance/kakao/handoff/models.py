# 담당: [C] | 책임: [C] Handoff 임시 데이터 모델
# 구현할 기능: 해시·만료·사용 시각·최소 응답; 카카오 사용자 ID 원문 과도 보관 금지
# 코드 경계: 카카오→웹 토큰만 다룬다. JWT 로그인 인증 수단으로 사용하지 않는다.
# 완료 기준: 정상·오류·권한/저장 실패 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A04·A05 요청·응답 모양 (openapi.yaml 0.2.0 HandoffPayload). 값은 contracts/domain.py를 따른다."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from inheritance.contracts.domain import AnswerChoice, Relationship, RiskId


class CamelModel(BaseModel):
    # JSON 이름은 camelCase(I01, 협의 1). 정의되지 않은 필드는 거절한다.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class HandoffRisk(CamelModel):
    risk_id: RiskId
    answer: AnswerChoice


class HandoffPayload(CamelModel):
    relationship: Relationship
    death_date: date | None
    death_date_unknown: bool
    one_stop_application: AnswerChoice
    # 답한 위험 질문만 담는다. 빈 목록은 '미응답'이며 '아니요'와 다르다.
    risks: list[HandoffRisk] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _check(self) -> HandoffPayload:
        # deathDate가 null이면 deathDateUnknown은 true, 날짜가 있으면 false (불일치는 422).
        if self.death_date_unknown == (self.death_date is not None):
            raise ValueError("deathDate와 deathDateUnknown이 맞지 않습니다")
        if self.death_date is not None and self.death_date > date.today():
            raise ValueError("deathDate는 미래일 수 없습니다")
        ids = [risk.risk_id for risk in self.risks]
        if len(ids) != len(set(ids)):
            raise ValueError("같은 riskId가 두 번 들어 있습니다")
        return self


class IssueResponse(CamelModel):
    token: str
    expires_in_seconds: int


class ExchangeRequest(CamelModel):
    token: str = Field(min_length=1, max_length=200)
