# 담당: [통합] | 책임: 앱과 요청에 필요한 공통 의존성 조립.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-4
# 구현할 기능: 요청별 DB 세션과 승인된 ModelPort·SearchPort·LawPort를 주입한다.
# 완료 기준: 라우터가 소유 기능을 구현하지 않고 필요한 의존성을 받는다.
# 제한사항: 도메인 규칙과 외부 SDK 구현을 이 파일에 두지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""A08 채팅 서비스 조립. backend는 llm·rag의 공개 계약(contracts)만 안다.

실제 Gemini·RAG·법령 구현은 backend 밖의 실행 진입점이 만들어 `create_app(chat_service=...)`로 넘긴다.
팀 결정(2026-10-23): ModelPort·SearchPort·LawPort가 **모두** 있어야 A08을 연다.
하나라도 없으면 None이고, A08은 스트림을 열기 전에 503 PROVIDER_UNAVAILABLE을 돌려준다.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from starter_llm.contracts.errors import ModelError
from starter_llm.contracts.ports import ModelPort
from starter_rag.contracts.ports import SearchPort

from inheritance.chat.services.answer import ChatAnswerService, V1ChatAnswerService
from inheritance.chat.services.question_router import ModelQuestionRouter
from inheritance.contracts.law import LawPort
from inheritance.law.mcp_client import KoreanLawMcp
from inheritance.law.open_api import LawOpenApiAddenda
from inheritance.law.service import LawLookupService

# purpose("classifier" | "answer")를 받아 ModelPort를 돌려준다. 분류와 답변은 공급자 설정이 따로다.
ModelFactory = Callable[[str], ModelPort]


def build_chat_service(
    model_factory: ModelFactory | None,
    search: SearchPort | None,
    law: LawPort | None,
) -> ChatAnswerService | None:
    if model_factory is None or search is None or law is None:
        return None
    try:
        classifier, answer = model_factory("classifier"), model_factory("answer")
    except (ModelError, ValueError):
        # 키가 없거나 설정이 잘못되면 호출 전에 막는다. 원인 문구에 비밀값이 섞일 수 있어 버린다.
        return None
    return V1ChatAnswerService(ModelQuestionRouter(classifier), search, law, answer)


# 법령 조회는 backend 안의 구현이라 여기서 바로 만든다(#94). LAW_OC가 없으면 None.
# 실행 진입점은 이 값을 build_chat_service의 law로 넘긴다. Node(npx)가 없으면 호출 시 S6이다.
def law_from_env() -> LawPort | None:
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        return None
    return LawLookupService(KoreanLawMcp(), LawOpenApiAddenda(oc))
