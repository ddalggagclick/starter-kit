# 담당: [통합] | 책임: 서비스 간 공개 Port의 Fake 구현 호환성 검사.
# 구현할 기능: I02·I03·I07·I09·I11·I19 시그니처, 호출 형태와 의존 경계 검증.
# 코드 경계: 테스트 전용 Fake만 두며 제품 구현·외부 서비스 호출은 추가하지 않는다.
# 완료 기준: 공개 DTO·동기/비동기·스트림 계약과 Backend Port 의존 경계를 검증한다.
"""공개 Port를 Fake로 연결해 호출 호환성과 의존 경계를 검사한다."""

from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import unittest
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

ROOT = Path(__file__).resolve().parents[1]
for source_root in ("llm", "rag", "backend/src"):
    sys.path.insert(0, str(ROOT / source_root))

from inheritance.contracts.checklist import ChecklistService, GuidanceInput
from inheritance.contracts.domain import (
    GuidanceResult,
    InitialAnswers,
    ProcedureGuidance,
    RiskAnswer,
)
from inheritance.contracts.law import LawLookupResult, LawPort, LawQuery
from inheritance.contracts.routing import QuestionRouterPort, RouteDecision
from inheritance.core.app_ports import AppServicePorts
from inheritance.kakao.adapter import KakaoInputAdapter
from starter_llm.contracts.models import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    ModelMessage,
)
from starter_llm.contracts.ports import ModelPort
from starter_rag.contracts.models import SearchRequest, SearchResult
from starter_rag.contracts.ports import SearchPort


def _guidance_result() -> GuidanceResult:
    return GuidanceResult(
        procedures=tuple(ProcedureGuidance(f"p{index:02d}") for index in range(1, 9)),
        guidance={"source": "fake"},
        risk_information={"source": "fake"},
        content_version="fake-guidance-v1",
    )


class FakeChecklistService:
    def __init__(self, result: GuidanceResult) -> None:
        self.result = result
        self.requests: list[GuidanceInput] = []

    def build_guidance(self, request: GuidanceInput) -> GuidanceResult:
        self.requests.append(request)
        return self.result


class FakeKakaoInputAdapter:
    def __init__(self, result: GuidanceInput) -> None:
        self.result = result
        self.requests: list[Mapping[str, Any]] = []

    def parse(self, skill_request: Mapping[str, Any]) -> GuidanceInput:
        self.requests.append(skill_request)
        return self.result


class FakeQuestionRouter:
    def __init__(self, decision: RouteDecision) -> None:
        self.decision = decision
        self.questions: list[str] = []

    async def classify(self, question: str) -> RouteDecision:
        self.questions.append(question)
        return self.decision


class FakeModel:
    def __init__(self, result: GenerationResult, chunks: tuple[GenerationChunk, ...]) -> None:
        self.result = result
        self.chunks = chunks
        self.generated_requests: list[GenerationRequest] = []
        self.streamed_requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.generated_requests.append(request)
        return self.result

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationChunk]:
        self.streamed_requests.append(request)

        async def iter_chunks() -> AsyncIterator[GenerationChunk]:
            for chunk in self.chunks:
                yield chunk

        return iter_chunks()


class FakeSearch:
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        self.requests: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> SearchResult:
        self.requests.append(request)
        return self.result


class FakeLaw:
    def __init__(self, result: LawLookupResult) -> None:
        self.result = result
        self.queries: list[LawQuery] = []

    async def lookup(self, query: LawQuery) -> LawLookupResult:
        self.queries.append(query)
        return self.result


@dataclass
class FakeAppServicePorts:
    model: ModelPort
    search: SearchPort
    law: LawPort
    checklist: ChecklistService


class FakePortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = InitialAnswers("spouse", None, True, "unknown")
        self.risk = RiskAnswer("debt", "unknown")
        self.guidance_input = GuidanceInput(self.initial, (self.risk,))
        self.generation_request = GenerationRequest(
            (ModelMessage("user", "합성 테스트 질문"),), "fake-profile", "fake-request"
        )

    def _assert_method_matches(self, port: type, fake: type, method_name: str) -> None:
        port_method = getattr(port, method_name)
        fake_method = getattr(fake, method_name)
        port_signature = inspect.signature(port_method)
        fake_signature = inspect.signature(fake_method)

        self.assertEqual(tuple(port_signature.parameters)[1:], tuple(fake_signature.parameters)[1:])
        self.assertEqual(get_type_hints(port_method), get_type_hints(fake_method))
        self.assertEqual(
            inspect.iscoroutinefunction(port_method),
            inspect.iscoroutinefunction(fake_method),
        )

    def test_fake_methods_match_all_public_port_signatures(self) -> None:
        port_fakes = (
            (ChecklistService, FakeChecklistService, "build_guidance"),
            (KakaoInputAdapter, FakeKakaoInputAdapter, "parse"),
            (QuestionRouterPort, FakeQuestionRouter, "classify"),
            (ModelPort, FakeModel, "generate"),
            (ModelPort, FakeModel, "stream"),
            (SearchPort, FakeSearch, "search"),
            (LawPort, FakeLaw, "lookup"),
        )
        for port, fake, method_name in port_fakes:
            with self.subTest(port=port.__name__, method=method_name):
                self._assert_method_matches(port, fake, method_name)

    def test_kakao_output_can_be_passed_to_checklist_service(self) -> None:
        payload = {"synthetic": True}
        adapter = FakeKakaoInputAdapter(self.guidance_input)
        result = _guidance_result()
        checklist = FakeChecklistService(result)

        parsed = adapter.parse(payload)
        guidance = checklist.build_guidance(parsed)

        self.assertEqual(adapter.requests, [payload])
        self.assertIs(checklist.requests[0], self.guidance_input)
        self.assertIs(guidance, result)
        self.assertEqual(len(guidance.procedures), 8)

    def test_question_router_returns_route_decision_asynchronously(self) -> None:
        decision = RouteDecision(
            "BOTH", needs_addenda=True, law_names=("민법",), article_numbers=("1019",)
        )
        router = FakeQuestionRouter(decision)

        result = asyncio.run(router.classify("합성 질문"))

        self.assertEqual(router.questions, ["합성 질문"])
        self.assertIs(result, decision)

    def test_model_supports_async_generation_and_async_iterator_stream(self) -> None:
        result = GenerationResult("완성 답변", "gemini", "fake-model")
        chunks = (GenerationChunk("완성 "), GenerationChunk("답변", done=True))
        model = FakeModel(result, chunks)

        generated = asyncio.run(model.generate(self.generation_request))
        stream = model.stream(self.generation_request)
        received = asyncio.run(self._collect(stream))

        self.assertIs(generated, result)
        self.assertEqual(model.generated_requests, [self.generation_request])
        self.assertEqual(model.streamed_requests, [self.generation_request])
        self.assertEqual(received, list(chunks))

    async def _collect(self, chunks: AsyncIterator[GenerationChunk]) -> list[GenerationChunk]:
        return [chunk async for chunk in chunks]

    def test_search_port_allows_zero_evidence_result(self) -> None:
        request = SearchRequest("합성 안내 질문")
        search = FakeSearch(SearchResult(()))

        result = asyncio.run(search.search(request))

        self.assertEqual(search.requests, [request])
        self.assertEqual(result, SearchResult(()))

    def test_law_port_represents_unverified_lookup_without_evidence(self) -> None:
        query = LawQuery("합성 법령 질문")
        law = FakeLaw(LawLookupResult("not_found", ()))

        result = asyncio.run(law.lookup(query))

        self.assertEqual(law.queries, [query])
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.evidence, ())

    def test_i19_fake_bundle_uses_declared_port_types(self) -> None:
        self.assertEqual(
            get_type_hints(AppServicePorts),
            {
                "model": ModelPort,
                "search": SearchPort,
                "law": LawPort,
                "checklist": ChecklistService,
            },
        )
        self.assertEqual(get_type_hints(FakeAppServicePorts), get_type_hints(AppServicePorts))
        bundle = FakeAppServicePorts(
            FakeModel(GenerationResult("답", "gemini", "fake-model"), ()),
            FakeSearch(SearchResult(())),
            FakeLaw(LawLookupResult("unavailable", ())),
            FakeChecklistService(_guidance_result()),
        )

        self.assertIs(bundle.model.__class__, FakeModel)
        self.assertIs(bundle.search.__class__, FakeSearch)
        self.assertIs(bundle.law.__class__, FakeLaw)
        self.assertIs(bundle.checklist.__class__, FakeChecklistService)

    def test_backend_imports_llm_and_rag_public_contracts_only(self) -> None:
        forbidden_modules: list[str] = []
        backend_root = ROOT / "backend" / "src" / "inheritance"
        for source in backend_root.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                imported: tuple[str, ...] = ()
                if isinstance(node, ast.Import):
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = (node.module,)
                forbidden_modules.extend(
                    module
                    for module in imported
                    if module in ("starter_llm", "starter_rag")
                    or module.startswith(("starter_llm.", "starter_rag."))
                    and not module.startswith(("starter_llm.contracts.", "starter_rag.contracts."))
                )

        self.assertEqual(forbidden_modules, [])


if __name__ == "__main__":
    unittest.main()
