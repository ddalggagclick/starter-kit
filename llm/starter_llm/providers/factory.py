# 담당: [C] | 책임: 승인된 설정에 따른 LLM 공급자 선택.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4
# 구현할 기능: Gemini 기본 + Groq(선택 Ollama) 자동 전환(3-2-4, 2026-10-21 변경)을 ModelPort 뒤에 둔다.
# 완료 기준: 생성·분류 호출이 공개 ModelPort 계약을 따른다.
# 제한사항: 설정한 순서 밖의 자동 전환 금지. 같은 공급자 반복 재시도 금지.
from __future__ import annotations

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.ports import ModelPort
from starter_llm.providers.failover import FailoverModel
from starter_llm.providers.gemini import create_gemini
from starter_llm.providers.groq import create_groq
from starter_llm.providers.ollama import create_ollama
from starter_llm.runtime.settings import LLMSettings, ProviderTarget


def _create_one(settings: LLMSettings, target: ProviderTarget) -> ModelPort:
    if target.provider == "gemini":
        return create_gemini(target.model, settings.gemini_api_key)
    if target.provider == "groq":
        return create_groq(target.model, settings.groq_api_key)
    if target.provider == "ollama":
        return create_ollama(target.model, settings.ollama_base_url)
    raise ModelError(ModelErrorCode.UNSUPPORTED_CAPABILITY, "init")


def create_model(settings: LLMSettings, purpose: str = "answer") -> ModelPort:
    """purpose: 'answer'(최종 생성) 또는 'classifier'(분류).

    키가 있는 공급자만 순서대로 묶는다(ollama는 키가 필요 없다). 둘 이상이면 FailoverModel,
    하나뿐이면 단일 공급자를 돌려준다. 사용할 수 있는 공급자가 없으면 호출 전에 거부한다.
    """
    chain = [t for t in settings.chain_for(purpose) if settings.api_key_configured(t.provider)]
    if not chain:
        return _create_one(settings, settings.target_for(purpose))  # 키가 없어 여기서 거부된다
    ports = [_create_one(settings, t) for t in chain]
    if len(ports) == 1:
        return ports[0]
    return FailoverModel(ports, settings.failover_policy)
