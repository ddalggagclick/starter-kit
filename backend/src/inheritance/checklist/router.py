# 담당: [B] | 책임: [B] 초기 질문·추천 결과 API 진입
# 구현할 기능: 요청/응답 명세는 API 담당자가 작성; 입력 검증 실패와 도메인 오류 분리
# 코드 경계: 8개 절차의 추천 규칙은 서버 한 곳에서만 구현한다. HTTP 타입은 API 담당자가 제공한다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A07 절차 8개 목록·상세 조회. 데이터는 checklist/procedures.py의 정적 데이터(D5)."""

from __future__ import annotations

from fastapi import APIRouter

from inheritance.checklist.procedures import PROCEDURE_DETAILS, PROCEDURE_SUMMARIES
from inheritance.checklist.rules import CONTENT_VERSION
from inheritance.checklist.schemas import ProcedureDetailResponse, ProcedureListResponse
from inheritance.contracts.domain import ProcedureId

router = APIRouter(prefix="/api/procedures", tags=["procedures"])


@router.get("", response_model=ProcedureListResponse, operation_id="A07_listProcedures")
async def list_procedures() -> ProcedureListResponse:
    return ProcedureListResponse(procedures=PROCEDURE_SUMMARIES, content_version=CONTENT_VERSION)


# procedureId는 p01~p08만 받는다. 그 밖의 값은 422 VALIDATION_ERROR(openapi 404 제안은 김선 님 확인 대상).
@router.get(
    "/{procedure_id}",
    response_model=ProcedureDetailResponse,
    operation_id="A07_getProcedure",
)
async def get_procedure(procedure_id: ProcedureId) -> ProcedureDetailResponse:
    detail = PROCEDURE_DETAILS[procedure_id]
    return ProcedureDetailResponse(**detail.model_dump(), content_version=CONTENT_VERSION)
