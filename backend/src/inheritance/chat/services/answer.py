# 담당: [B] | 책임: 근거 검색과 최종 답변 생성을 조립한다.
# PRD: E3 / 스토리 3-2, 3-3, 3-4, 3-5 / 태스크 3-2-3, 3-3-2, 3-3-3, 3-4-1, 3-5-3.
# 구현할 기능: SearchPort·LawPort 결과를 소비하고 근거가 있을 때 최종 답변을 한 번 생성한다.
# 완료 기준: 검증된 답변만 반환하고 S6·S7·S9를 구분한다.
# 제한사항: 프롬프트와 인용 검증은 전담 모듈에 위임한다. 근거가 없으면 최종 답변을 생성하지 않는다.
# 상태: PRD 태스크 미시작. Fake 계약 검증은 테스트 영역의 책임이다.
"""채팅 서비스 연결점. 실제 알고리즘과 API 엔드포인트는 담당자 구현 PR에서 작성."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from starter_llm.contracts.errors import ModelError
from starter_llm.contracts.models import GenerationRequest
from starter_llm.contracts.ports import ModelPort
from starter_rag.contracts.models import Evidence, SearchRequest
from starter_rag.contracts.ports import SearchPort

from inheritance.chat.safety import (
    SOURCE_UNAVAILABLE,
    SafetyDecision,
    classify_model_error,
)
from inheritance.chat.services.citation_validation import (
    CitationMismatch,
    CitationValidator,
    CitationValidatorPort,
    extract_cited_ids,
)
from inheritance.chat.services.context import validate_chat_input
from inheritance.chat.services.prompt_builder import AnswerPromptBuilder, AnswerPromptBuilderPort
from inheritance.contracts.chat import AnswerOutcome
from inheritance.contracts.law import LawEvidence, LawPort, LawQuery
from inheritance.contracts.routing import QuestionRouterPort, RouteDecision
from inheritance.core.errors import ErrorCode

ANSWER_MODEL_PROFILE = "answer"

# 진행 단계 이름은 openapi SseStatusEvent.stage 값과 같다. 실제로 그 단계를 시작할 때만 알린다.
AnswerStage = Literal["searching", "lawChecking", "writing"]
ProgressCallback = Callable[[AnswerStage], Awaitable[None]]


@dataclass(frozen=True)
class ChatAnswerResult:
    outcome: AnswerOutcome
    # S6·S9일 때 HTTP 오류 코드(429/503/504 선택용). answered·abstained(S7)는 None이다.
    error_code: ErrorCode | None = None
    # abstained(S7) 사유(openapi SseResultEvent.reasonCode). 근거 0건·인용 불일치만 값을 둔다.
    reason_code: ErrorCode | None = None


class ChatAnswerService(Protocol):
    # 성공·부분 답변에만 검증된 출처를 담고, 오류·유보 결과에는 본문을 담지 않는다.
    # 취소된 요청은 None(보낼 결과 없음)을 돌려준다. 입력 정책 위반은 ValueError다.
    async def answer(
        self,
        question: str,
        request_id: str,
        previous_questions: tuple[str, ...] = (),
        progress: ProgressCallback | None = None,
    ) -> ChatAnswerResult | None: ...


# 주의: QuestionRouterPort.classify()가 Gemini ModelPort.generate() 한 번 호출한다.
# 최종 답변 작성은 ModelPort.stream() 한 번. 재심사 LLM/자동 Ollama 전환 금지.
# 경로 분류는 근거가 아니다. 검증된 출처만 AnswerOutcome.references로 내보낸다.


class _SourceUnavailable(Exception):
    pass


class V1ChatAnswerService:
    # 질문 원문·답변 본문은 로그에 남기지 않고 저장하지 않는다.
    def __init__(
        self,
        router: QuestionRouterPort,
        search: SearchPort,
        law: LawPort,
        model: ModelPort,
        prompts: AnswerPromptBuilderPort | None = None,
        validator: CitationValidatorPort | None = None,
    ) -> None:
        self._router = router
        self._search = search
        self._law = law
        self._model = model
        self._prompts = prompts or AnswerPromptBuilder()
        self._validator = validator or CitationValidator()

    async def answer(
        self,
        question: str,
        request_id: str,
        previous_questions: tuple[str, ...] = (),
        progress: ProgressCallback | None = None,
    ) -> ChatAnswerResult | None:
        validate_chat_input(question, previous_questions)
        notify = progress or _no_progress

        try:
            decision = await self._router.classify(question)
        except ModelError as exc:
            safety = classify_model_error(exc.code, "classify")
            if safety.action != "continue_as_both":
                return _finish(safety, request_id)
            decision = RouteDecision("BOTH")

        try:
            rag, laws = await self._gather(question, decision, notify)
        except _SourceUnavailable:
            return _finish(SOURCE_UNAVAILABLE, request_id)
        # 근거 0건이면 최종 생성을 하지 않는다 (INTERFACE 3장).
        if not rag and not laws:
            return _withheld(request_id, ErrorCode.SOURCE_NOT_VERIFIED)

        messages = self._prompts.build(question, rag, laws, previous_questions)
        request = GenerationRequest(messages, ANSWER_MODEL_PROFILE, request_id)
        await notify("writing")
        try:
            text = await self._collect(request)
        except ModelError as exc:
            return _finish(classify_model_error(exc.code, "answer"), request_id)

        # 검증 전 본문은 밖으로 내보내지 않는다. 인용이 실제 근거와 맞을 때만 answered.
        try:
            references = self._validator.validate_and_resolve(extract_cited_ids(text), rag, laws)
        except CitationMismatch:
            return _withheld(request_id, ErrorCode.CITATION_MISMATCH)
        return ChatAnswerResult(AnswerOutcome("answered", text, references, request_id))

    async def _gather(
        self, question: str, decision: RouteDecision, notify: ProgressCallback
    ) -> tuple[tuple[Evidence, ...], tuple[LawEvidence, ...]]:
        rag: tuple[Evidence, ...] = ()
        laws: tuple[LawEvidence, ...] = ()
        if decision.route in ("RAG", "BOTH"):
            await notify("searching")
            try:
                rag = (await self._search.search(SearchRequest(question))).evidence
            except Exception as exc:
                # 검색 구현의 예외 종류는 RAG 내부 사항이라 모두 기술 오류(S6)로 본다.
                raise _SourceUnavailable from exc
        if decision.route in ("LAW", "BOTH"):
            query = LawQuery(
                question=question,
                applicable_date=decision.reference_date,
                law_names=decision.law_names,
                article_numbers=decision.article_numbers,
                needs_addenda=decision.needs_addenda,
            )
            await notify("lawChecking")
            try:
                result = await self._law.lookup(query)
            except Exception as exc:
                raise _SourceUnavailable from exc
            # not_found·ambiguous는 근거 0건(S7)으로, unavailable은 기술 오류(S6)로 본다.
            if result.status == "unavailable":
                raise _SourceUnavailable
            laws = result.evidence
        return rag, laws

    # stream()을 정확히 한 번 부르고 서버 안에서 전체 본문을 모은다.
    async def _collect(self, request: GenerationRequest) -> str:
        parts: list[str] = []
        async for chunk in self._model.stream(request):
            parts.append(chunk.text_delta)
        return "".join(parts)


async def _no_progress(stage: AnswerStage) -> None:
    return None


def _withheld(request_id: str, reason: ErrorCode) -> ChatAnswerResult:
    outcome = AnswerOutcome("abstained", None, (), request_id)
    return ChatAnswerResult(outcome, None, reason)


def _finish(safety: SafetyDecision, request_id: str) -> ChatAnswerResult | None:
    if safety.action == "drop" or safety.status is None:
        return None
    return ChatAnswerResult(AnswerOutcome(safety.status, None, (), request_id), safety.error_code)
