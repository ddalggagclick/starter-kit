# 담당: [B] | 책임: [B] 추천 기능 API용 스키마 자리
# 구현할 기능: 초기·위험 답변과 추천 DTO 연결; API 담당 승인 전 JSON 세부 필드 확정 금지
# 코드 경계: 8개 절차의 추천 규칙은 서버 한 곳에서만 구현한다. HTTP 타입은 API 담당자가 제공한다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A07 절차 목록·상세 응답 모양 (openapi.yaml ProcedureDetail). JSON 이름은 camelCase(I01)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from inheritance.contracts.domain import ProcedureId


class CamelModel(BaseModel):
    # 정적 데이터를 담는 응답 모델이라 만든 뒤 바꾸지 못하게 한다.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class ProcedureSummary(CamelModel):
    procedure_id: ProcedureId
    name: str
    summary: str


class ProcedureListResponse(CamelModel):
    procedures: tuple[ProcedureSummary, ...] = Field(min_length=8, max_length=8)
    # 2-2-2: 카카오(체크리스트 규칙)와 같은 안내 콘텐츠 버전(rules.CONTENT_VERSION 한 곳에서 정한다).
    content_version: str


class OfficialLink(CamelModel):
    title: str
    url: str


class ProcedureDetail(CamelModel):
    procedure_id: ProcedureId
    action: str
    deadline: str
    risk: str
    agency: str
    documents: tuple[str, ...]
    methods: tuple[str, ...]
    exceptions: tuple[str, ...]
    contacts: tuple[str, ...]
    official_links: tuple[OfficialLink, ...]
    # 함께 보면 좋은 절차는 D4 보류라 지금은 항상 빈 목록이다.
    related_procedure_ids: tuple[ProcedureId, ...] = Field(default=(), max_length=3)


class ProcedureDetailResponse(ProcedureDetail):
    # 2-2-2: 카카오와 같은 안내 콘텐츠 버전.
    content_version: str
