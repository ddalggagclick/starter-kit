"""[C] llm/ 단위 테스트. 모두 가짜 모델(네트워크·키 없음). 실제 Gemini 호출 성공을 주장하지 않는다."""

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from starter_llm.cli import main
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, ModelMessage
from starter_llm.contracts.ports import ModelPort
from starter_llm.providers._base import LangChainModel, classify_exception
from starter_llm.providers.gemini import create_gemini
from starter_llm.runtime.client import ManagedModelResources
from starter_llm.runtime.settings import LLMSettings, SettingsError


def req(text="안녕", timeout=5.0):
    return GenerationRequest(
        messages=(ModelMessage(role="user", content=text),),
        model_profile="answer",
        request_id="r1",
        timeout_seconds=timeout,
    )


class Boom:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    async def ainvoke(self, _):
        self.calls += 1
        raise self.exc

    def astream(self, _):
        async def gen():
            self.calls += 1
            raise self.exc
            yield  # pragma: no cover

        return gen()


class HttpError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("secret-prompt-text")


def fake(text="답변입니다"):
    return GenericFakeChatModel(messages=iter([AIMessage(content=text)]))


async def test_generate_ok():
    m = LangChainModel(fake(), "gemini", "m")
    r = await m.generate(req())
    assert r.text == "답변입니다" and r.provider == "gemini"


async def test_stream_chunks_then_done():
    m = LangChainModel(fake("가 나 다"), "gemini", "m")
    chunks = [c async for c in m.stream(req())]
    assert "".join(c.text_delta for c in chunks) == "가 나 다"
    assert chunks[-1].done is True and chunks[-1].text_delta == ""


async def test_429_is_rate_limit_and_not_retried():
    chat = Boom(HttpError(429))
    m = LangChainModel(chat, "gemini", "m")
    with pytest.raises(ModelError) as e:
        await m.generate(req())
    assert e.value.code is ModelErrorCode.RATE_LIMIT and e.value.retryable is False
    assert chat.calls == 1  # 재시도 없음
    assert "secret-prompt-text" not in str(e.value)  # 원문 미포함


async def test_429_stream():
    m = LangChainModel(Boom(HttpError(429)), "gemini", "m")
    with pytest.raises(ModelError) as e:
        async for _ in m.stream(req()):
            pass
    assert e.value.code is ModelErrorCode.RATE_LIMIT


async def test_timeout():
    class Slow:
        async def ainvoke(self, _):
            await asyncio.sleep(5)

    m = LangChainModel(Slow(), "gemini", "m")
    with pytest.raises(ModelError) as e:
        await m.generate(req(timeout=0.05))
    assert e.value.code is ModelErrorCode.TIMEOUT


async def test_unavailable_and_empty_output():
    with pytest.raises(ModelError) as e:
        await LangChainModel(Boom(HttpError(503)), "gemini", "m").generate(req())
    assert e.value.code is ModelErrorCode.UNAVAILABLE
    with pytest.raises(ModelError) as e2:
        await LangChainModel(fake("  "), "gemini", "m").generate(req())
    assert e2.value.code is ModelErrorCode.INVALID_OUTPUT


def test_classify():
    assert classify_exception(HttpError(429), "r").code is ModelErrorCode.RATE_LIMIT
    assert classify_exception(HttpError(504), "r").code is ModelErrorCode.TIMEOUT
    assert classify_exception(RuntimeError("x"), "r").code is ModelErrorCode.UNAVAILABLE


def test_gemini_without_key_rejected_before_call():
    with pytest.raises(ModelError):
        create_gemini("m", api_key="")


def test_port_shape():
    m: ModelPort = LangChainModel(fake(), "gemini", "m")
    assert hasattr(m, "generate") and hasattr(m, "stream")


def test_settings_defaults_and_secret_hidden():
    s = LLMSettings.from_env({"GEMINI_API_KEY": "SECRET123"})
    assert s.answer.provider == "gemini" and s.classifier.provider == "gemini"
    assert "SECRET123" not in repr(s)
    assert s.selection.auto_fallback is False


def test_settings_rejects_auto_fallback_and_bad_provider():
    with pytest.raises(SettingsError):
        LLMSettings.from_env({"LLM_AUTO_FALLBACK": "true"})
    with pytest.raises(SettingsError):
        LLMSettings.from_env({"LLM_PROVIDER": "openai"})


def test_settings_ollama_not_primary():
    with pytest.raises(SettingsError):
        LLMSettings.from_env({"LLM_PROVIDER": "ollama"})


def test_settings_failover_defaults_groq_with_separate_keys():
    s = LLMSettings.from_env({"GEMINI_API_KEY": "G-SECRET", "GROQ_API_KEY": "Q-SECRET"})
    assert [x.provider for x in s.failover_answer] == ["groq"]
    assert [x.provider for x in s.failover_classifier] == ["groq"]
    assert s.failover_answer[0].model == "openai/gpt-oss-120b"
    assert "G-SECRET" not in repr(s) and "Q-SECRET" not in repr(s)
    assert s.key_for("gemini") == "G-SECRET" and s.key_for("groq") == "Q-SECRET"


def test_settings_failover_off():
    s = LLMSettings.from_env({"LLM_FAILOVER_PROVIDERS": "none"})
    assert s.failover_answer == () and s.failover_classifier == ()


def test_settings_failover_chain_with_ollama_and_validation():
    s = LLMSettings.from_env({"LLM_FAILOVER_PROVIDERS": "groq,ollama", "LLM_OLLAMA_MODEL": "m1"})
    assert [x.provider for x in s.chain_for("answer")] == ["gemini", "groq", "ollama"]
    assert s.chain_for("answer")[2].model == "m1"
    assert s.failover_policy.order == ("gemini", "groq", "ollama")
    for bad in ("openai", "groq,groq"):
        with pytest.raises(SettingsError):
            LLMSettings.from_env({"LLM_FAILOVER_PROVIDERS": bad})


def test_failover_policy_order_validation():
    from starter_llm.contracts.profiles import FailoverPolicy

    FailoverPolicy()
    FailoverPolicy(order=("gemini", "groq", "ollama"))
    for bad in ((), ("gemini", "gemini"), ("gemini", "openai")):
        with pytest.raises(ValueError):
            FailoverPolicy(order=bad)


async def test_resource_manager_lazy_single_create_and_idle_close():
    made = []

    def factory(settings, purpose):
        made.append(purpose)
        return LangChainModel(fake(), "gemini", "m")

    mgr = ManagedModelResources(LLMSettings.from_env({}), factory)
    a, b = await asyncio.gather(mgr.acquire("answer"), mgr.acquire("answer"))
    assert a is b and made == ["answer"]
    await mgr.close_idle(1000)  # 활성 임대 중에는 닫지 않음
    assert (await mgr.acquire("answer")) is a
    for _ in range(3):
        await mgr.release("answer")
    await mgr.close_idle(299)
    assert (await mgr.acquire("answer")) is a  # 300초 미만이면 유지
    await mgr.release("answer")
    await mgr.close_idle(300)
    c = await mgr.acquire("answer")
    assert c is not a and made == ["answer", "answer"]
    await mgr.shutdown()


def test_cli_status_offline(capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET123")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "SECRET123" not in out and '"generationImplemented": true' in out


def test_cli_validate_bad_timeout():
    with pytest.raises(SystemExit) as e:
        main(["validate", "--prompt", "x", "--timeout", "0"])
    assert e.value.code == 2


# ---------------- 3-2-4 자동 전환 (Gemini -> Groq) ----------------
from starter_llm.providers.failover import FailoverModel


class Fixed:
    """가짜 공급자: 정해진 결과 또는 오류를 돌려주고 호출 횟수를 센다."""

    def __init__(self, provider, text="ok", error=None, chunks=None):
        self.provider, self.text, self.error, self.chunks = provider, text, error, chunks
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if self.error:
            raise ModelError(self.error, request.request_id)
        from starter_llm.contracts.models import GenerationResult

        return GenerationResult(text=self.text, provider=self.provider, model="m")

    def stream(self, request):
        from starter_llm.contracts.models import GenerationChunk

        async def gen():
            self.calls += 1
            for i, c in enumerate(self.chunks or [self.text]):
                if self.error and i == (self.fail_at if hasattr(self, "fail_at") else 0):
                    raise ModelError(self.error, request.request_id)
                yield GenerationChunk(text_delta=c)
            yield GenerationChunk(text_delta="", done=True)

        return gen()


async def test_failover_primary_ok_no_switch():
    g, q = Fixed("gemini"), Fixed("groq")
    r = await FailoverModel([g, q]).generate(req())
    assert r.provider == "gemini" and g.calls == 1 and q.calls == 0


@pytest.mark.parametrize(
    "code", [ModelErrorCode.RATE_LIMIT, ModelErrorCode.UNAVAILABLE, ModelErrorCode.TIMEOUT]
)
async def test_failover_switches_once(code):
    g, q = Fixed("gemini", error=code), Fixed("groq", text="대체")
    r = await FailoverModel([g, q]).generate(req())
    assert r.provider == "groq" and r.text == "대체"
    assert g.calls == 1 and q.calls == 1  # 반복 재시도 없음


async def test_failover_invalid_output_not_switched():
    g, q = Fixed("gemini", error=ModelErrorCode.INVALID_OUTPUT), Fixed("groq")
    with pytest.raises(ModelError) as e:
        await FailoverModel([g, q]).generate(req())
    assert e.value.code is ModelErrorCode.INVALID_OUTPUT and q.calls == 0


async def test_failover_both_rate_limited_returns_rate_limit_once_each():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT)
    q = Fixed("groq", error=ModelErrorCode.RATE_LIMIT)
    with pytest.raises(ModelError) as e:
        await FailoverModel([g, q]).generate(req())
    assert e.value.code is ModelErrorCode.RATE_LIMIT
    assert g.calls == 1 and q.calls == 1


async def test_failover_both_fail_mixed_keeps_rate_limit():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT)
    q = Fixed("groq", error=ModelErrorCode.UNAVAILABLE)
    with pytest.raises(ModelError) as e:
        await FailoverModel([g, q]).generate(req())
    assert e.value.code is ModelErrorCode.RATE_LIMIT


async def test_failover_cooldown_skips_primary_after_429():
    now = [0.0]
    g, q = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT), Fixed("groq")
    m = FailoverModel([g, q], clock=lambda: now[0])
    await m.generate(req())
    await m.generate(req())  # 쿨다운 중: Gemini 호출 없이 Groq
    assert g.calls == 1 and q.calls == 2
    now[0] = 61.0
    await m.generate(req())  # 쿨다운 끝: Gemini를 다시 1회 시도
    assert g.calls == 2


async def test_failover_unavailable_does_not_cooldown():
    g, q = Fixed("gemini", error=ModelErrorCode.UNAVAILABLE), Fixed("groq")
    m = FailoverModel([g, q])
    await m.generate(req())
    await m.generate(req())
    assert g.calls == 2


async def test_failover_stream_switch_before_first_chunk():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT, chunks=["a"])
    q = Fixed("groq", chunks=["가", "나"])
    out = [c.text_delta async for c in FailoverModel([g, q]).stream(req())]
    assert "".join(out) == "가나" and g.calls == 1 and q.calls == 1


async def test_failover_stream_no_switch_after_partial_output():
    g = Fixed("gemini", error=ModelErrorCode.UNAVAILABLE, chunks=["가", "나"])
    g.fail_at = 1  # 첫 청크 송출 뒤 실패
    q = Fixed("groq", chunks=["x"])
    got = []
    with pytest.raises(ModelError):
        async for c in FailoverModel([g, q]).stream(req()):
            got.append(c.text_delta)
    assert got == ["가"] and q.calls == 0  # 이어 붙이지 않음


def test_factory_builds_failover_only_when_both_keys():
    from starter_llm.providers.factory import create_model

    both = LLMSettings.from_env({"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"})
    assert isinstance(create_model(both), FailoverModel)
    only_g = LLMSettings.from_env({"GEMINI_API_KEY": "g"})
    assert not isinstance(create_model(only_g), FailoverModel)
    only_q = LLMSettings.from_env({"GROQ_API_KEY": "q"})
    assert create_model(only_q).provider == "groq"  # 기본 키가 없으면 Groq만으로 동작
    with pytest.raises(ModelError):
        create_model(LLMSettings.from_env({}))  # 키가 없으면 호출 전에 거부


def test_cli_generate_no_keys_exit3(monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert main(["generate", "--prompt", "안녕"]) == 3


def test_cli_status_shows_failover_without_secrets(capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "G-SECRET")
    monkeypatch.setenv("GROQ_API_KEY", "Q-SECRET")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "SECRET" not in out and '"groqApiKeyConfigured": true' in out and "groq" in out


# ---------------- 3개 순서 전환 (Gemini -> Groq -> Ollama) ----------------
async def test_chain_three_providers_each_once():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT)
    q = Fixed("groq", error=ModelErrorCode.UNAVAILABLE)
    o = Fixed("ollama", text="로컬")
    r = await FailoverModel([g, q, o]).generate(req())
    assert r.provider == "ollama" and (g.calls, q.calls, o.calls) == (1, 1, 1)


async def test_chain_all_fail_keeps_rate_limit_and_each_called_once():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT)
    q = Fixed("groq", error=ModelErrorCode.TIMEOUT)
    o = Fixed("ollama", error=ModelErrorCode.UNAVAILABLE)
    with pytest.raises(ModelError) as e:
        await FailoverModel([g, q, o]).generate(req())
    assert e.value.code is ModelErrorCode.RATE_LIMIT
    assert (g.calls, q.calls, o.calls) == (1, 1, 1)


async def test_chain_last_provider_always_tried_even_in_cooldown():
    now = [0.0]
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT)
    q = Fixed("groq", error=ModelErrorCode.RATE_LIMIT)
    m = FailoverModel([g, q], clock=lambda: now[0])
    for _ in range(2):
        with pytest.raises(ModelError):
            await m.generate(req())
    assert g.calls == 1 and q.calls == 2  # Gemini는 쿨다운으로 건너뛰고 마지막(Groq)은 계속 시도


async def test_chain_stream_goes_through_to_third():
    g = Fixed("gemini", error=ModelErrorCode.RATE_LIMIT, chunks=["a"])
    q = Fixed("groq", error=ModelErrorCode.UNAVAILABLE, chunks=["b"])
    o = Fixed("ollama", chunks=["다", "라"])
    out = [c.text_delta async for c in FailoverModel([g, q, o]).stream(req())]
    assert "".join(out) == "다라" and (g.calls, q.calls, o.calls) == (1, 1, 1)


def test_factory_chain_with_ollama_needs_no_key():
    from starter_llm.providers.factory import create_model

    s = LLMSettings.from_env(
        {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q", "LLM_FAILOVER_PROVIDERS": "groq,ollama"}
    )
    m = create_model(s)
    assert isinstance(m, FailoverModel) and len(m._ports) == 3
    only_ollama = LLMSettings.from_env({"LLM_FAILOVER_PROVIDERS": "ollama"})
    assert create_model(only_ollama).provider == "ollama"  # 클라우드 키가 없어도 로컬 Ollama로 동작
