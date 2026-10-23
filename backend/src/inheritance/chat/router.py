# 담당: [B] | 책임: 채팅 요청·취소·진행 상태·검증된 답변의 HTTP 진입점.
# PRD: E3 / 스토리 3-1, 3-5 / 태스크 3-1-4, 3-5-2.
# 구현할 기능: 요청 ID로 한 번에 하나의 요청을 관리하고 취소 신호를 서비스에 전달한다.
# 완료 기준: 취소·연결 종료 시 해당 요청만 정리하고 늦은 결과를 전송하지 않는다.
# 제한사항: LLM·RAG 구현을 직접 import하지 않는다. SSE 이벤트와 HTTP 상세는 API 담당자 승인 후 적용한다.
# 상태: PRD 태스크 미시작.
"""A08 `POST /api/ai/ask` (openapi.yaml A08_askAi). 응답은 text/event-stream: status 여러 번 → result 또는 error 1번.

검증된 완성 답변만 result로 보낸다. 연결이 끊기면 진행 중인 서비스 작업을 취소하고 늦은 결과를 보내지 않는다.
질문 원문·답변 본문은 로그에 남기지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from inheritance.chat.schemas import AskRequest
from inheritance.chat.services.answer import AnswerStage, ChatAnswerResult, ChatAnswerService
from inheritance.chat.services.context import validate_chat_input
from inheritance.core.errors import HTTP_STATUS, ErrorCode, error_body

router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)


# 서버 시작 시 core/dependencies.py가 조립한 서비스를 쓴다(main.py → app.state.chat_service).
# 모델·검색·법령 중 하나라도 없으면 None이라 스트림을 열기 전에 503 PROVIDER_UNAVAILABLE을 돌려준다.
def get_chat_service(request: Request) -> ChatAnswerService | None:
    return getattr(request.app.state, "chat_service", None)


@router.post("/ask", operation_id="A08_askAi", response_model=None)
async def ask_ai(
    body: AskRequest, service: Annotated[ChatAnswerService | None, Depends(get_chat_service)]
) -> StreamingResponse | JSONResponse:
    previous = tuple(body.previous_questions)
    try:
        validate_chat_input(body.question, previous)
    except ValueError:
        code = ErrorCode.VALIDATION_ERROR
        raise HTTPException(HTTP_STATUS[code], detail={"code": code.value}) from None
    if service is None:
        code = ErrorCode.PROVIDER_UNAVAILABLE
        return JSONResponse(error_body(code), status_code=HTTP_STATUS[code])
    return StreamingResponse(
        _events(service, body.question, body.request_id, previous),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 서비스는 별도 작업으로 돌리고, 진행 단계와 최종 결과를 큐로 받아 순서대로 내보낸다.
async def _events(
    service: ChatAnswerService, question: str, request_id: str, previous: tuple[str, ...]
) -> AsyncIterator[str]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    started = time.perf_counter()

    async def progress(stage: AnswerStage) -> None:
        await queue.put(_sse("status", {"stage": stage}))

    async def run() -> None:
        try:
            result = await service.answer(question, request_id, previous, progress)
        except Exception as exc:  # noqa: BLE001 - 스트림 경계에서 내부 오류를 S6 이벤트로 바꾼다.
            # 예상하지 못한 내부 오류도 본문 없이 S6로 끝낸다. 로그에는 예외 종류 이름만 남긴다.
            _log(request_id, "technical_error", type(exc).__name__, started)
            await queue.put(_error_event(ErrorCode.PROVIDER_UNAVAILABLE, request_id))
        else:
            # None은 취소된 요청이다. 보낼 결과가 없다.
            if result is not None:
                _log(request_id, result.outcome.status, _code(result), started)
                await queue.put(_result_event(result))
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())
    try:
        while (event := await queue.get()) is not None:
            yield event
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def _result_event(result: ChatAnswerResult) -> str:
    outcome = result.outcome
    if result.error_code is not None:
        return _error_event(result.error_code, outcome.request_id)
    if outcome.status in ("answered", "partial"):
        data = {
            "state": "answered",
            "answer": outcome.answer_text,
            "sources": [{"title": r.title, "url": r.official_url} for r in outcome.references],
        }
    else:
        # 출처 0건·인용 불일치·답변 형식 오류는 판단 유보(S7). 오류가 아니다.
        # 사유: 근거 0건 SOURCE_NOT_VERIFIED, 인용 불일치 CITATION_MISMATCH, 그 밖(답변 형식 오류)은 null.
        reason = result.reason_code.value if result.reason_code is not None else None
        data = {"state": "withheld", "answer": None, "sources": [], "reasonCode": reason}
    # remainingToday(A10)는 횟수 저장 방식 결정 전이라 null로 보낸다.
    return _sse("result", {"reasonCode": None, **data, "remainingToday": None})


def _error_event(code: ErrorCode, request_id: str) -> str:
    return _sse("error", {**error_body(code), "requestId": request_id})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _code(result: ChatAnswerResult) -> str | None:
    return result.error_code.value if result.error_code is not None else None


# 허용 필드만 넘긴다(PRD 7-4-3). trace_id는 화면이 만든 요청 번호다.
def _log(request_id: str, status: str, error_code: str | None, started: float) -> None:
    logger.info(
        "chat.ask",
        extra={
            "event": "chat.ask",
            "status": status,
            "error_code": error_code,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "trace_id": request_id,
        },
    )
