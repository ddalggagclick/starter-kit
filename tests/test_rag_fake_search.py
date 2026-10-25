"""RAG의 품질 검증 이전 모의 SearchPort 동작을 확인한다."""

from __future__ import annotations

import asyncio
import inspect
import sys
import unittest
from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from starter_rag.contracts.models import SearchRequest, SearchResult
from starter_rag.contracts.ports import SearchPort
from starter_rag.retrieval.fake_search import FakeSearchPort, make_fixed_evidence
from starter_rag.retrieval.search import PGVectorSearch


class FixedEvidenceTests(unittest.TestCase):
    def test_고정_근거에_합성_출처_정보가_포함된다(self) -> None:
        # Evidence와 SourceRef의 필수 필드가 채워지고, HTTPS 및 example.invalid 주소와
        # 합성 표기를 통해 실제 기관의 검증된 자료로 오인되지 않는지 확인한다.
        # 기대값: 모든 필수 필드가 비어 있지 않고, URL은 HTTPS이며 합성 식별자가 포함된다.
        evidence = make_fixed_evidence()

        self.assertTrue(evidence.evidence_id)
        self.assertTrue(evidence.text)
        self.assertTrue(evidence.location)
        self.assertTrue(evidence.source.source_id)
        self.assertTrue(evidence.source.title)
        self.assertTrue(evidence.source.url.startswith("https://"))
        self.assertTrue(evidence.source.publisher)
        self.assertTrue(evidence.source.version)
        self.assertIn("synthetic", evidence.evidence_id)
        self.assertIn("합성", evidence.source.title)
        self.assertIn("합성", evidence.source.publisher)
        self.assertIn("example.invalid", evidence.source.url)

    def test_고정_근거는_반복_생성해도_동일하다(self) -> None:
        # fixture가 시각이나 난수 같은 가변 상태에 의존하지 않는지 확인한다.
        # 기대값: 두 번 생성한 Evidence의 모든 필드가 같아 DTO 동등 비교가 참이다.
        self.assertEqual(make_fixed_evidence(), make_fixed_evidence())


class FakeSearchEvidenceTests(unittest.TestCase):
    def test_근거_시나리오는_고정_Evidence를_SearchResult로_반환한다(self) -> None:
        # evidence 시나리오를 명시한 FakeSearchPort가 I09 비동기 호출로 동작하는지 확인한다.
        # 기대값: 반환 타입은 SearchResult이고 evidence는 고정 fixture 한 건과 같다.
        request = SearchRequest("합성 안내 질문")
        search = FakeSearchPort(scenario="evidence")

        result = asyncio.run(search.search(request))

        self.assertIsInstance(result, SearchResult)
        self.assertEqual(result.evidence, (make_fixed_evidence(),))

    def test_검색_메서드가_기존_SearchPort_시그니처와_호환된다(self) -> None:
        # 구현 메서드가 기존 Port의 self/request 파라미터 구조와 입력·출력 타입을 지키는지 확인한다.
        # 기대값: 파라미터 이름·종류가 같고, 해석한 타입 힌트도 SearchRequest→SearchResult다.
        fake_signature = inspect.signature(FakeSearchPort.search)
        port_signature = inspect.signature(SearchPort.search)
        self.assertEqual(
            tuple((name, parameter.kind) for name, parameter in fake_signature.parameters.items()),
            tuple((name, parameter.kind) for name, parameter in port_signature.parameters.items()),
        )
        self.assertEqual(get_type_hints(FakeSearchPort.search), get_type_hints(SearchPort.search))

    def test_검색_결과는_요청한_top_k를_초과하지_않는다(self) -> None:
        # 계약 허용값인 top_k 1, 3, 10에서 검색 결과 수 상한을 확인한다.
        # 기대값: 각 요청의 Evidence 수는 해당 top_k 이하이며 고정 fixture는 최대 한 건이다.
        search = FakeSearchPort(scenario="evidence")

        for top_k in (1, 3, 10):
            with self.subTest(top_k=top_k):
                result = asyncio.run(search.search(SearchRequest("합성 질문", top_k)))
                self.assertLessEqual(len(result.evidence), top_k)


class FakeSearchEmptyTests(unittest.TestCase):
    def test_빈_시나리오는_근거가_없는_SearchResult를_반환한다(self) -> None:
        # 근거 부족 시나리오가 예외나 HTTP 응답 대신 유효한 검색 DTO를 반환하는지 확인한다.
        # 기대값: 결과 타입은 SearchResult이고 evidence는 빈 tuple이다.
        search = FakeSearchPort(scenario="empty")

        result = asyncio.run(search.search(SearchRequest("합성 안내 질문")))

        self.assertIsInstance(result, SearchResult)
        self.assertEqual(result.evidence, ())

    def test_두_시나리오는_서로_독립적으로_동작한다(self) -> None:
        # 인스턴스별 시나리오가 서로의 결과를 바꾸지 않는지 확인한다.
        # 기대값: evidence는 빈 시나리오 실행 전후 모두 같은 한 건, empty는 계속 빈 tuple이다.
        evidence_search = FakeSearchPort(scenario="evidence")
        empty_search = FakeSearchPort(scenario="empty")
        request = SearchRequest("합성 안내 질문")

        evidence_before = asyncio.run(evidence_search.search(request))
        empty_result = asyncio.run(empty_search.search(request))
        evidence_after = asyncio.run(evidence_search.search(request))

        self.assertEqual(evidence_before.evidence, (make_fixed_evidence(),))
        self.assertEqual(empty_result.evidence, ())
        self.assertEqual(evidence_after, evidence_before)

    def test_지원하지_않는_시나리오는_생성할_수_없다(self) -> None:
        # 호출자가 지원하지 않는 시나리오명을 지정했을 때 생성 단계에서 검증하는지 확인한다.
        # 기대값: 'unknown' 설정으로 FakeSearchPort를 만들면 ValueError가 발생한다.
        with self.assertRaises(ValueError):
            FakeSearchPort(scenario="unknown")  # type: ignore[arg-type]


class PublishedEvidenceAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_게시자료는_주소가_없어도_출처정보를_유지한다(self) -> None:
        from types import SimpleNamespace

        class Embedding:
            async def embed_query(self, _: str) -> tuple[float, ...]:
                return (0.0,) * 768

        class Store:
            async def search_vectors(self, vector, *, top_k, allow_synthetic):
                self.assert_args = (len(vector), top_k, allow_synthetic)
                return (
                    SimpleNamespace(
                        chunk_id="guide-chunk-1",
                        text="사용 설명서의 절차 안내",
                        cosine_distance=0.25,
                        metadata={
                            "source_id": "guide-001",
                            "source_title": "사용 설명서",
                            "source_url": None,
                            "publisher": "Example",
                            "version": "1.0",
                            "location": "manual.pdf page=2",
                            "publication_state": "published",
                            "is_synthetic": False,
                        },
                    ),
                )

        store = Store()
        result = await PGVectorSearch(store, Embedding()).search(SearchRequest("절차 안내"))

        self.assertEqual(store.assert_args, (768, 10, False))
        self.assertEqual(len(result.evidence), 1)
        evidence = result.evidence[0]
        self.assertEqual(evidence.evidence_id, "guide-chunk-1")
        self.assertEqual(evidence.source.source_id, "guide-001")
        self.assertEqual(evidence.source.title, "사용 설명서")
        self.assertIsNone(evidence.source.url)
        self.assertEqual(evidence.source.publisher, "Example")
        self.assertEqual(evidence.source.version, "1.0")
        self.assertEqual(evidence.text, "사용 설명서의 절차 안내")
        self.assertEqual(evidence.location, "manual.pdf page=2")
        self.assertEqual(evidence.score, 0.75)


if __name__ == "__main__":
    unittest.main()
