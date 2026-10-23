"""가짜 저장소와 임베딩으로 계약을 검증하며 실제 pgvector를 사용하지 않는다."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from starter_rag.contracts.models import DocumentVersion, Evidence, SearchRequest, SourceRef


def _load_without_database(name: str, relative_path: str, stub_name: str, stub_class: str):
    """RAG 런타임 의존성을 불러오지 않고 어댑터를 분리해 테스트한다."""
    stub = types.ModuleType(stub_name)
    setattr(stub, stub_class, type(stub_class, (), {}))
    package_dir = Path(__file__).resolve().parents[1] / "rag" / "starter_rag"
    spec = importlib.util.spec_from_file_location(name, package_dir / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter module is missing")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {stub_name: stub, name: module}):
        spec.loader.exec_module(module)
    return module


class PublicationValidationTests(unittest.TestCase):
    def test_출처정보는주소없음을허용하고잘못된주소를거부한다(self):
        module = _load_without_database(
            "isolated_publication",
            "storage/publication.py",
            "starter_rag.storage.database",
            "PostgresRagDatabase",
        )
        row = {
            "source_id": "U-TEST",
            "source_title": "기관 안내",
            "source_url": None,
            "publisher": "기관",
            "version": "v2",
            "location": "Source_v2!A2",
        }
        self.assertTrue(module._has_publishable_provenance([row]))
        for url in (
            "",
            "http://example.org",
            "https://",
            "https://space host",
            "https://user:password@example.org",
            123,
        ):
            with self.subTest(url=url):
                self.assertFalse(module._has_publishable_provenance([{**row, "source_url": url}]))
        self.assertFalse(module._has_publishable_provenance([{**row, "location": ""}]))
        self.assertTrue(
            module._has_publishable_provenance([{**row, "source_url": "https://example.org"}])
        )

    def test_문서출처의누락된주소를유지한다(self):
        module = _load_without_database(
            "isolated_publication",
            "storage/publication.py",
            "starter_rag.storage.database",
            "PostgresRagDatabase",
        )
        row = {
            "source_id": "U-TEST",
            "source_title": "안내",
            "source_url": None,
            "publisher": "기관",
            "version": "v2",
            "content_sha256": "abc",
        }
        result = module._document_version(row, "published", 3)
        self.assertIsNone(result.source.url)
        self.assertEqual(result.chunk_count, 3)


class EvidenceUrlContractTests(unittest.TestCase):
    def test_주소가없는출처도게시와근거계약을만족한다(self):
        source = SourceRef(
            source_id="U-06-BANK-HANA",
            title="하나은행 상속예금 안내",
            url=None,
            publisher="하나은행",
            version="source-v2-test",
        )

        evidence = Evidence(
            evidence_id="sha256:test",
            source=source,
            text="상속예금 확인 안내",
            location="Source_v2.xlsx!RAG_Unit본문!row=2",
            score=0.75,
        )
        version = DocumentVersion(source, "a" * 64, "published", 1)

        self.assertIsNone(evidence.source.url)
        self.assertEqual(evidence.evidence_id, "sha256:test")
        self.assertEqual(evidence.source.source_id, "U-06-BANK-HANA")
        self.assertEqual(evidence.source.title, "하나은행 상속예금 안내")
        self.assertEqual(evidence.source.publisher, "하나은행")
        self.assertEqual(evidence.source.version, "source-v2-test")
        self.assertEqual(evidence.text, "상속예금 확인 안내")
        self.assertEqual(evidence.location, "Source_v2.xlsx!RAG_Unit본문!row=2")
        self.assertEqual(evidence.score, 0.75)
        self.assertEqual(version.state, "published")

    def test_주소가있으면유효한Https만계약을만족한다(self):
        for url in ("http://example.org", "https://", "https://user:password@example.org"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                SourceRef("U-TEST", "기관 안내", url, "기관", "v1")

        source = SourceRef("U-TEST", "기관 안내", "https://example.org/guide", "기관", "v1")
        self.assertEqual(source.url, "https://example.org/guide")


class SearchAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_주소없이도링크를만들지않고근거를반환한다(self):
        module = _load_without_database(
            "isolated_search",
            "retrieval/search.py",
            "starter_rag.storage.vector_store",
            "PGVectorStore",
        )
        from types import SimpleNamespace

        class Embedding:
            async def embed_query(self, _: str) -> tuple[float, ...]:
                return (0.0,) * 768

        class Store:
            async def search_vectors(self, vector, *, top_k, allow_synthetic):
                self.assert_args = (len(vector), top_k, allow_synthetic)

                def hit(identifier, url, state="published", synthetic=False):
                    return SimpleNamespace(
                        chunk_id=identifier,
                        text="실제 데이터 대신 단위 테스트 샘플",
                        cosine_distance=0.25,
                        metadata={
                            "source_id": "U-TEST",
                            "source_title": "기관 안내",
                            "source_url": url,
                            "publisher": "기관",
                            "version": "v2",
                            "location": "unit row=2; official position unverified",
                            "publication_state": state,
                            "is_synthetic": synthetic,
                        },
                    )

                return (
                    hit("none", None),
                    hit("http", "http://example.org"),
                    hit("https", "https://official.example.org/source"),
                    hit("malformed", "https://"),
                    hit("hidden", None),
                    hit("indexed", None, "indexed"),
                    hit("synthetic", None, "published", True),
                )

        store = Store()
        result = await module.PGVectorSearch(store, Embedding()).search(
            SearchRequest("절차 질문", top_k=5)
        )
        self.assertEqual(store.assert_args, (768, 5, False))
        self.assertEqual([x.evidence_id for x in result.evidence], ["none", "https", "hidden"])
        self.assertEqual(
            [item.source.url for item in result.evidence],
            [None, "https://official.example.org/source", None],
        )
        self.assertEqual(result.evidence[0].score, 0.75)


if __name__ == "__main__":
    unittest.main()
