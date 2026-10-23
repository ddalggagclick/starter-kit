# 담당: [통합] 실행 진입점 초안, 구현 B1 김현주 (수빈 님 확인 전 제안) | 책임: 실제 부품을 조립해 앱을 띄운다.
# 구현할 기능: llm·rag·법령 구현을 만들어 create_app(chat_service=...)로 넘긴다.
# 완료 기준: 모델·검색·법령이 모두 준비되면 A08이 실제로 답하고, 하나라도 없으면 503이다.
# 제한사항: backend/src/inheritance 안에서는 llm·rag 구현을 import할 수 없어(시험으로 검사) 이 파일이 그 경계 밖에 있다.
"""실행: `uv run uvicorn app_entry:app --app-dir backend --port 8000` (저장소 루트에서).

`inheritance.main:app`은 지금처럼 부품 없이 뜬다(A08 503). 실제 채팅이 필요한 실행·배포는 이 모듈을 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable

from inheritance.core.dependencies import ModelFactory, build_chat_service, law_from_env
from inheritance.main import create_app
from starter_llm.contracts.ports import ModelPort
from starter_rag.contracts.ports import SearchPort


# Gemini 기본 + LLM_FAILOVER_PROVIDERS 순서 전환(3-2-4). 설정이 잘못되면 None(A08 503).
def model_factory_from_env() -> ModelFactory | None:
    from starter_llm.providers.factory import create_model
    from starter_llm.runtime.settings import LLMSettings

    try:
        settings = LLMSettings.from_env()
    except ValueError:
        return None

    def factory(purpose: str) -> ModelPort:
        return create_model(settings, purpose)

    return factory


# TODO(RAG 담당): starter_rag가 SearchPort를 만들어 주는 공개 함수를 내주면 여기서 부른다.
def search_from_env() -> SearchPort | None:
    return None


def build_app(
    model_factory: Callable[[], ModelFactory | None] = model_factory_from_env,
    search: Callable[[], SearchPort | None] = search_from_env,
) -> object:
    service = build_chat_service(model_factory(), search(), law_from_env())
    return create_app(chat_service=service)


app = build_app()
