# 책임: [통합] FastAPI 앱 조립과 실행 진입점을 관리한다.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-4 (앱 조립 지원)
# 구현할 기능: 승인된 의존성과 업무 라우터를 앱 수명주기에 맞게 조립한다.
# 완료 기준: 앱 조립·종료 시 필요한 의존성을 안전하게 시작하고 정리한다.
# 현재 상태: /health와 CORS만 연결된 최소 실행 스캐폴드다.
# 제한사항: API 상세 계약과 DB 스키마 승인 전에 경로·스키마·테이블을 확정하지 않는다.
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from inheritance.auth.router import auth_service_from_env, create_auth_router
from inheritance.chat import router as chat_router
from inheritance.chat.services.answer import ChatAnswerService
from inheritance.chat.usage_limit import GuestDailyLimiter, member_limiter_from_env
from inheritance.checklist import router as checklist_router
from inheritance.checklist.server_router import create_server_checklist_router
from inheritance.checklist.server_storage import InMemoryServerChecklistStore
from inheritance.core.errors import install_error_handlers
from inheritance.core.health import router as health_router
from inheritance.core.origin import DEFAULT_FRONTEND_ORIGIN
from inheritance.core.safe_logging import install_safe_logging
from inheritance.core.security import install_cors_origins
from inheritance.kakao.handoff import router as handoff_router

HANDOFF_PURGE_INTERVAL_SECONDS = 60


# 발급·교환 요청이 없어도 10분 지난 인계 답변이 메모리에 남지 않게 주기적으로 지운다.
async def _purge_handoff_periodically() -> None:
    while True:
        await asyncio.sleep(HANDOFF_PURGE_INTERVAL_SECONDS)
        handoff_router.service.purge_expired()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_purge_handoff_periodically())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# Health·인계·절차·AI 질문 라우터와 CORS를 구성한다. 인증·DB Settings는 업무 라우터 조립 전까지 읽지 않는다.
def create_app(chat_service: ChatAnswerService | None = None) -> FastAPI:
    # 로그는 허용된 6개 필드만 출력한다(PRD 7-4-3). 원문·토큰·비밀값은 남지 않는다.
    install_safe_logging()
    app = FastAPI(
        title="상속길잡이 Backend",
        version="0.1.0",
        description="최소 실행 앱: health·카카오 인계·절차 목록·AI 질문 연결됨",
        lifespan=lifespan,
    )
    install_cors_origins(app, (os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),))
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(handoff_router.router)
    app.include_router(checklist_router.router)
    app.include_router(chat_router.router)
    # 인증(A11~A16)과 A17 서버 체크리스트는 JWT·CSRF 비밀값이 있을 때만 연다. 저장소는 ERD 승인 전이라 메모리다.
    app.state.auth_service = None
    # A08 비회원 하루 10회 제한(3-7-2). 로그인 사용자는 auth_service로 구분해 제한하지 않는다.
    app.state.guest_limiter = GuestDailyLimiter()
    # 로그인 사용자 채팅 1분 10회(3-7-3, CHAT_RATE_LIMIT_PER_MINUTE).
    app.state.member_limiter = member_limiter_from_env()
    if (auth := auth_service_from_env()) is not None:
        service, security = auth
        checklist_store = InMemoryServerChecklistStore()
        service.on_account_deleted(checklist_store.delete)  # 탈퇴 시 서버 체크리스트도 삭제(5-4-2)
        app.include_router(create_auth_router(service, security))
        app.include_router(create_server_checklist_router(checklist_store, service, security))
        app.state.auth_service = service  # A08이 로그인 사용자와 비회원을 구분할 때 쓴다.
    # A08 서비스는 실행 진입점이 core/dependencies.build_chat_service로 만들어 넘긴다. 없으면 503.
    app.state.chat_service = chat_service
    # TODO [통합/API 담당]: 업무 router 및 lifespan 의존성 구성은 ERD/API 승인 후 연결한다.
    return app


app = create_app()
