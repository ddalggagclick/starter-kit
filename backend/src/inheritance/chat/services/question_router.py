# 담당: [B] | 책임: 질문을 RAG·LAW·BOTH 검색 경로로 분류한다.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-1, 3-2-2, 3-2-5.
# 구현할 기능: ModelPort.generate() 1회로 분류 JSON을 받아 RouteDecision으로 바꾼다.
# 완료 기준: 형식 오류는 MODEL_INVALID_OUTPUT으로 알려 채팅 서비스가 BOTH로 이어 간다.
# 제한사항: 모델이 낸 법령명·조문·기준일은 검색 후보일 뿐 확정값이 아니다. 질문 원문을 로그에 남기지 않는다.
"""질문을 RAG·LAW·BOTH로 분류하는 QuestionRouterPort 구현 (PRD 3-2-1, 3-2-2, 3-2-5).

ModelPort.generate()를 model_profile="classifier"로 정확히 한 번 부른다. 분류 결과는 화면에 보여주지 않는다.
분류 JSON 모양은 llm 쪽 Fake ModelPort와 맞춘 약속이다(2026-10-22 김선 합의).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, ModelMessage
from starter_llm.contracts.ports import ModelPort

from inheritance.contracts.routing import RouteDecision

CLASSIFIER_MODEL_PROFILE = "classifier"

# V1 임시 지시문(검수 전). JSON 모양을 바꾸면 llm/starter_llm/providers/fake.py와 함께 바꾼다.
CLASSIFIER_SYSTEM_PROMPT = (
    "질문을 RAG(상속 절차·서류·신청 안내), LAW(법령 조문·부칙), BOTH 중 하나로 분류하세요.\n"
    "모호하면 BOTH로 답하세요.\n"
    '조문 번호는 "제1019조"처럼 문자열로 적으세요.\n'
    "아래 모양의 JSON 하나만 출력하세요.\n"
    '{"route": "RAG|LAW|BOTH", "lawNames": [], "articleNumbers": [], '
    '"referenceDate": null, "needsAddenda": false}'
)

_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class ModelQuestionRouter:
    def __init__(self, model: ModelPort) -> None:
        self._model = model

    # 질문만 사용자 메시지로 보낸다. 요청 ID는 계약에 인자가 없어 분류할 때마다 새로 만든다.
    async def classify(self, question: str) -> RouteDecision:
        request = GenerationRequest(
            messages=(
                ModelMessage("system", CLASSIFIER_SYSTEM_PROMPT),
                ModelMessage("user", question),
            ),
            model_profile=CLASSIFIER_MODEL_PROFILE,
            request_id=uuid.uuid4().hex,
        )
        result = await self._model.generate(request)
        return parse_route_decision(result.text, request.request_id)


# JSON이 아니거나 route가 세 값이 아니면 MODEL_INVALID_OUTPUT. 채팅 서비스가 이를 BOTH로 이어 간다.
# 법령 힌트는 검색 조건 후보일 뿐이라, 이상한 값은 버리고 분류 전체를 실패시키지 않는다(3-2-2).
def parse_route_decision(text: str, request_id: str) -> RouteDecision:
    try:
        data = json.loads(_CODE_FENCE.sub("", text.strip()))
    except ValueError:
        raise ModelError(ModelErrorCode.INVALID_OUTPUT, request_id) from None
    if not isinstance(data, dict) or data.get("route") not in ("RAG", "LAW", "BOTH"):
        raise ModelError(ModelErrorCode.INVALID_OUTPUT, request_id)
    return RouteDecision(
        route=data["route"],
        needs_addenda=data.get("needsAddenda") is True,
        law_names=_hint_strings(data.get("lawNames")),
        article_numbers=_hint_articles(data.get("articleNumbers")),
        reference_date=_hint_date(data.get("referenceDate")),
    )


def _hint_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


# 모델이 조문 번호를 숫자(1019)나 숫자 글자("1019")로 보내도 "제1019조"로 받는다(#83).
# 그 밖의 값은 _hint_strings와 같이 다룬다. bool은 int의 하위 타입이라 따로 거른다.
def _hint_articles(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    articles = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool) and item > 0:
            articles.append(f"제{item}조")
        elif isinstance(item, str) and item.strip().isdecimal():
            articles.append(f"제{int(item.strip())}조")
        elif isinstance(item, str) and item.strip():
            articles.append(item.strip())
    return tuple(articles)


def _hint_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None
