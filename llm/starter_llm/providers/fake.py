# 담당: [C] | 책임: 시험·V1 모의 흐름용 Fake ModelPort (실제 LLM을 호출하지 않는다).
# 코드 경계: 네트워크·API 키 없이 동작한다. LangChain·공급자 SDK·backend를 import하지 않는다.
# 제한사항: 모의 결과는 실제 정확도·안전·응답 시간을 뜻하지 않는다. 답변 본문에 [모의 답변] 표시를 붙인다.
"""[C] Fake ModelPort.

- generate(): 분류용 JSON 텍스트를 반환한다. (model_profile="classifier"에 쓰는 형태)
- stream(): 모의 답변 조각을 반환한다. (model_profile="answer"에 쓰는 형태)
- 질문 안에 FAKE_* 표시가 있으면 해당 ModelError를 재현한다.

분류 JSON 모양(backend와의 약속):
{"route": "RAG|LAW|BOTH", "lawNames": [], "articleNumbers": [], "referenceDate": null, "needsAddenda": false}
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationChunk, GenerationRequest, GenerationResult

FAKE_MODEL_NAME = "fake-model"

# 질문(메시지) 안에 이 문자열이 있으면 해당 오류를 재현한다.
FAILURE_MARKERS: dict[str, ModelErrorCode] = {
    "FAKE_RATE_LIMIT": ModelErrorCode.RATE_LIMIT,
    "FAKE_TIMEOUT": ModelErrorCode.TIMEOUT,
    "FAKE_UNAVAILABLE": ModelErrorCode.UNAVAILABLE,
    "FAKE_INVALID_OUTPUT": ModelErrorCode.INVALID_OUTPUT,
}
# 이 표시가 있으면 오류 대신 JSON이 아닌 텍스트를 반환한다. (분류 결과 형식 오류 재현)
BAD_JSON_MARKER = "FAKE_BAD_JSON"

LAW_KEYWORDS = ("민법", "법령", "조문", "부칙", "시행일", "개정")
RAG_KEYWORDS = ("절차", "서류", "신청", "기한", "어디서", "방법")
ANSWER_PREFIX = "[모의 답변] "
ANSWER_CHUNKS = ("공식 안내를 기준으로 ", "확인한 내용을 ", "정리했습니다.")

_ARTICLE = re.compile(r"제\s*(\d+)\s*조")


def _all_text(request: GenerationRequest) -> str:
    return "\n".join(m.content for m in request.messages)


def _question(request: GenerationRequest) -> str:
    """마지막 사용자 메시지를 질문으로 본다."""
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    return request.messages[-1].content


def _failure_for(request: GenerationRequest) -> ModelError | None:
    text = _all_text(request)
    for marker, code in FAILURE_MARKERS.items():
        if marker in text:
            return ModelError(code, request.request_id, retryable=False)
    return None


def classification_for(question: str) -> dict:
    """질문 글자만으로 정해진 분류 JSON을 만든다. 같은 질문은 항상 같은 결과다."""
    is_law = any(word in question for word in LAW_KEYWORDS)
    is_rag = any(word in question for word in RAG_KEYWORDS)
    if is_law and not is_rag:
        route = "LAW"
    elif is_rag and not is_law:
        route = "RAG"
    else:  # 둘 다이거나 어느 쪽도 아니면 BOTH
        route = "BOTH"
    law_names = ["민법"] if "민법" in question else []
    articles = [f"제{n}조" for n in _ARTICLE.findall(question)]
    return {
        "route": route,
        "lawNames": law_names if route != "RAG" else [],
        "articleNumbers": articles if route != "RAG" else [],
        "referenceDate": None,
        "needsAddenda": "부칙" in question,
    }


class FakeModel:
    """ModelPort 시그니처를 따르는 모의 모델. 호출 기록을 남겨 시험에서 확인할 수 있다."""

    provider = "gemini"  # Provider 값 중 하나여야 하므로 표시용으로만 사용한다.
    model = FAKE_MODEL_NAME

    def __init__(self) -> None:
        self.generated_requests: list[GenerationRequest] = []
        self.streamed_requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.generated_requests.append(request)
        error = _failure_for(request)
        if error is not None:
            raise error
        if BAD_JSON_MARKER in _all_text(request):
            text = "분류 결과 아님"
        else:
            text = json.dumps(classification_for(_question(request)), ensure_ascii=False)
        return GenerationResult(
            text=text, provider=self.provider, model=self.model, finish_reason="STOP"
        )

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]:
        self.streamed_requests.append(request)

        async def iterate() -> AsyncIterator[GenerationChunk]:
            error = _failure_for(request)
            if error is not None:  # 첫 조각을 내보내기 전에 실패한다.
                raise error
            yield GenerationChunk(text_delta=ANSWER_PREFIX)
            for piece in ANSWER_CHUNKS:
                yield GenerationChunk(text_delta=piece)
            yield GenerationChunk(text_delta="", done=True)

        return iterate()
