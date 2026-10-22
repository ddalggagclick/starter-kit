"""[C] ModelSelection이 Provider 타입(gemini/groq/ollama)과 일치하는지 확인한다 (PR #18 리뷰 반영)."""

import pytest
from starter_llm.contracts.profiles import ModelSelection
from starter_llm.runtime.settings import LLMSettings


def test_model_selection_accepts_all_provider_values():
    for p in ("gemini", "groq", "ollama"):
        assert ModelSelection(classification_provider=p, answer_provider=p).answer_provider == p


def test_model_selection_still_rejects_unknown_provider_and_auto_fallback():
    with pytest.raises(ValueError):
        ModelSelection(answer_provider="openai")
    with pytest.raises(ValueError):
        ModelSelection(auto_fallback=True)


def test_settings_selection_does_not_crash_with_groq_primary():
    s = LLMSettings.from_env({"LLM_PROVIDER": "groq", "CLASSIFIER_PROVIDER": "groq"})
    assert s.selection.answer_provider == "groq" and s.selection.auto_fallback is False
