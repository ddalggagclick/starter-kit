# 담당: [B] | 책임: A17 서버 체크리스트 저장·조회·삭제 HTTP 진입.
# PRD: E4 / 태스크 4-6-2, 4-5-3 (openapi A17 GET·PUT·DELETE /api/me/checklist).
# 구현할 기능: Access 토큰의 계정 것만 다루고, 상태 변경은 Origin·CSRF를 확인한다.
# 완료 기준: 미동의 조회 403, 다른 계정 접근 불가, 동의 철회 시 삭제.
# 제한사항: 체크리스트 원문을 로그에 남기지 않는다. 이 기기 기록과 자동 병합하지 않는다.
"""A17 `/api/me/checklist` (2026-10-26 팀 회의 결정, openapi 제안 → 확정 요청)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from inheritance.auth.router import user_id_from_bearer
from inheritance.auth.service import AuthService
from inheritance.checklist.server_storage import (
    InvalidItemStates,
    SavedChecklist,
    ServerChecklistStore,
    validate_item_states,
)
from inheritance.core.errors import HTTP_STATUS, ErrorCode
from inheritance.core.security import WebSecuritySettings, enforce_csrf


class ChecklistSave(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    item_states: list[Any]
    server_save_consent: bool


def _error(code: ErrorCode) -> HTTPException:
    return HTTPException(HTTP_STATUS[code] or 500, detail={"code": code.value})


def _body(saved: SavedChecklist) -> dict[str, Any]:
    return {"itemStates": list(saved.item_states), "serverSaveConsent": True}


def create_server_checklist_router(
    store: ServerChecklistStore, auth: AuthService, security: WebSecuritySettings
) -> APIRouter:
    router = APIRouter(prefix="/api/me/checklist", tags=["account"])

    def csrf(request: Request) -> None:
        enforce_csrf(request, security)

    checked = [Depends(csrf)]

    @router.get("", operation_id="A17_getChecklist")
    def get_checklist(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        user_id = user_id_from_bearer(auth, authorization)
        saved = store.get(user_id)
        if saved is None:
            # 서버 저장 동의가 없으면 본문 없이 거부한다(프론트는 '동의 없음'으로 처리).
            raise _error(ErrorCode.FORBIDDEN)
        return _body(saved)

    @router.put("", operation_id="A17_putChecklist", dependencies=checked)
    def put_checklist(
        body: ChecklistSave, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        user_id = user_id_from_bearer(auth, authorization)
        if not body.server_save_consent:
            # 동의 없이 저장하지 않는다. 철회는 DELETE로 한다.
            raise _error(ErrorCode.FORBIDDEN)
        try:
            item_states = validate_item_states(body.item_states)
        except InvalidItemStates:
            raise _error(ErrorCode.VALIDATION_ERROR) from None
        # 전체 덮어쓰기(충돌 시 마지막 저장이 남는다).
        return _body(store.put(user_id, item_states))

    @router.delete("", status_code=204, operation_id="A17_deleteChecklist", dependencies=checked)
    def delete_checklist(authorization: Annotated[str | None, Header()] = None) -> Response:
        user_id = user_id_from_bearer(auth, authorization)
        store.delete(user_id)
        return Response(status_code=204)

    return router
