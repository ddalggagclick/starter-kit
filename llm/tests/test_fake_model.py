"""[C] Fake ModelPort 시험 (네트워크·API 키 없이 실행). PRD 3-2-5 / V1 모의 경계."""

import asyncio
import inspect
import json

import pytest
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, ModelMessage
from starter_llm.contracts.ports import ModelPort
from starter_llm.providers.fake import ANSWER_PREFIX, FakeModel

KEYS = {"route", "lawNames", "articleNumbers", "referenceDate", "needsAddenda"}


def _req(text: str, profile: str = "classifier") -> GenerationRequest:
    return GenerationRequest(
        messages=(ModelMessage(role="user", content=text),),
        model_profile=profile,
        request_id="t1",
    )


def _classify(text: str) -> dict:
    result = asyncio.run(FakeModel().generate(_req(text)))
    return json.loads(result.text)


def _stream(text: str) -> list:
    async def run():
        return [c async for c in FakeModel().stream(_req(text, "answer"))]

    return asyncio.run(run())


def test_signature_matches_model_port():
    for name in ("generate", "stream"):
        assert list(inspect.signature(getattr(FakeModel, name)).parameters) == list(
            inspect.signature(getattr(ModelPort, name)).parameters
        )


@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("상속 신청 절차와 서류가 궁금합니다", "RAG"),
        ("민법 제1000조 조문을 알려 주세요", "LAW"),
        ("민법 조문과 신청 절차를 함께 알려 주세요", "BOTH"),
        ("그냥 궁금해서 물어봅니다", "BOTH"),
    ],
)
def test_classification_route(question, route):
    data = _classify(question)
    assert set(data) == KEYS
    assert data["route"] == route


def test_classification_law_hints_and_same_result_for_same_question():
    q = "민법 제1000조와 제1003조 부칙을 알려 주세요"
    data = _classify(q)
    assert data["lawNames"] == ["민법"]
    assert data["articleNumbers"] == ["제1000조", "제1003조"]
    assert data["needsAddenda"] is True
    assert data["referenceDate"] is None
    assert _classify(q) == data


def test_rag_route_has_no_law_hints():
    data = _classify("민법 상속 신청 절차")
    assert data["route"] == "BOTH"
    data = _classify("상속 신청 서류")
    assert data["route"] == "RAG" and data["lawNames"] == [] and data["articleNumbers"] == []


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        ("FAKE_RATE_LIMIT", ModelErrorCode.RATE_LIMIT),
        ("FAKE_TIMEOUT", ModelErrorCode.TIMEOUT),
        ("FAKE_UNAVAILABLE", ModelErrorCode.UNAVAILABLE),
        ("FAKE_INVALID_OUTPUT", ModelErrorCode.INVALID_OUTPUT),
    ],
)
def test_failure_markers_in_generate_and_stream(marker, code):
    with pytest.raises(ModelError) as e:
        asyncio.run(FakeModel().generate(_req(f"질문 {marker}")))
    assert e.value.code == code and e.value.request_id == "t1"
    with pytest.raises(ModelError) as e2:
        _stream(f"질문 {marker}")
    assert e2.value.code == code


def test_bad_json_marker_returns_non_json_text():
    result = asyncio.run(FakeModel().generate(_req("질문 FAKE_BAD_JSON")))
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.text)


def test_stream_yields_marked_answer_and_done_chunk():
    chunks = _stream("상속 절차")
    text = "".join(c.text_delta for c in chunks)
    assert text.startswith(ANSWER_PREFIX)
    assert chunks[-1].done is True and all(not c.done for c in chunks[:-1])


def test_stream_cites_first_evidence_id_in_request():
    text = "".join(c.text_delta for c in _stream("근거 [[E-1]] 와 [[E-2]] 로 답하십시오"))
    assert text.endswith(" [[E-1]]")
    assert "[[E-2]]" not in text


def test_stream_has_no_citation_without_evidence_id():
    text = "".join(c.text_delta for c in _stream("상속 절차"))
    assert "[[" not in text


def test_records_calls_and_marks_result_as_fake():
    model = FakeModel()
    asyncio.run(model.generate(_req("상속 절차")))

    async def run():
        return [c async for c in model.stream(_req("상속 절차", "answer"))]

    asyncio.run(run())
    assert len(model.generated_requests) == 1 and len(model.streamed_requests) == 1
    assert model.generated_requests[0].model_profile == "classifier"
    assert model.streamed_requests[0].model_profile == "answer"
    result = asyncio.run(model.generate(_req("상속 절차")))
    assert result.model == "fake-model"
