"""Pure validation checks for the local-only pgvector storage boundary."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from starter_rag.contracts.models import ChunkRecord, SearchRequest
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    database_url_from_environment,
    validate_local_database_url,
)
from starter_rag.storage.models import DEFAULT_COLLECTION_ID, RagTableTarget
from starter_rag.storage.publication import PostgresPublicationStore, PublicationError
from starter_rag.storage.vector_store import PGVectorStore, VectorIntegrityError


class _UnusedEmbedding:
    async def embed_query(self, text: str) -> tuple[float, ...]:
        return ()

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return ()


class _ConfiguredEmbedding:
    def __init__(self, vectors: tuple[tuple[float, ...], ...]) -> None:
        self.vectors = vectors

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return ()

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return self.vectors


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one(self):
        return self.value


class _RowsResult:
    def __init__(self, values) -> None:
        self.values = values

    def mappings(self):
        return self

    def all(self):
        return self.values


class _ReadConnection:
    def __init__(self) -> None:
        self.statements = []
        self.published_identity_rows = [
            {
                "content_sha256": "pdf-sha",
                "publication_state": "published",
                "metadata": {"hitl_review_sha256": "review-sha"},
                "source_title": "Guide 1",
                "publisher": "Publisher",
                "source_url": None,
            },
            {
                "content_sha256": "pdf-sha",
                "publication_state": "published",
                "metadata": {"hitl_review_sha256": "review-sha"},
                "source_title": "Guide 1",
                "publisher": "Publisher",
                "source_url": None,
            },
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append((sql, parameters))
        if "count(*)" in sql:
            return _ScalarResult(2)
        if "SELECT content_sha256, publication_state, metadata" in sql:
            return _RowsResult(self.published_identity_rows)
        if "SELECT chunk_id," in sql:
            return _RowsResult(
                [
                    {
                        "chunk_id": "chunk-a",
                        "collection_id": "collection-a",
                        "source_id": "source-a",
                        "version": "v1",
                        "publication_state": "published",
                    }
                ]
            )
        return None


class _ReadEngine:
    def __init__(self) -> None:
        self.connection = _ReadConnection()

    def connect(self):
        return self.connection


class StorageContractTests(unittest.TestCase):
    def test_게시_조회는_설정된_테이블과_컬렉션으로_범위를_제한한다(self) -> None:
        engine = _ReadEngine()
        database = SimpleNamespace(
            sql_engine=engine,
            target=RagTableTarget("configured_schema", "configured_chunks"),
        )
        publication = PostgresPublicationStore(database, collection_id="collection-a")
        vector_store = PGVectorStore(database, collection_id="collection-a")

        count = asyncio.run(publication.published_chunk_count("source-a", "v1"))
        identity = asyncio.run(publication._published_version_identity("source-a", "v1"))
        ids = asyncio.run(vector_store._published_chunk_ids(["chunk-a", "chunk-b"]))

        self.assertEqual(count, 2)
        self.assertIsNotNone(identity)
        self.assertEqual(identity.chunk_count, 2)
        self.assertEqual(identity.content_sha256, "pdf-sha")
        self.assertEqual(identity.review_sha256, "review-sha")
        self.assertEqual(identity.source_title, "Guide 1")
        self.assertEqual(identity.publisher, "Publisher")
        self.assertIsNone(identity.source_url)
        self.assertEqual(ids, {"chunk-a"})
        queries = [sql for sql, _ in engine.connection.statements if "SELECT" in sql]
        self.assertEqual(len(queries), 3)
        self.assertTrue(all('"configured_schema"."configured_chunks"' in sql for sql in queries))
        self.assertIn("publication_state = 'published'", queries[0])
        self.assertIn("collection_id = :collection_id", queries[1])
        self.assertIn("publication_state = :publication_state", queries[2])
        self.assertIn("collection_id = :collection_id", queries[2])
        self.assertTrue(all("rag_test.chunks" not in sql for sql in queries))
        params = [params for sql, params in engine.connection.statements if "SELECT" in sql]
        self.assertTrue(all(param["collection_id"] == "collection-a" for param in params))
        self.assertEqual(params[2]["publication_state"], "published")

    def test_일부_청크만_게시된_버전은_재사용_대상으로_돌려주지_않는다(self) -> None:
        engine = _ReadEngine()
        engine.connection.published_identity_rows = [
            {
                "content_sha256": "pdf-sha",
                "publication_state": "published",
                "metadata": {"hitl_review_sha256": "review-sha"},
            },
            {
                "content_sha256": "pdf-sha",
                "publication_state": "indexed",
                "metadata": {"hitl_review_sha256": "review-sha"},
            },
        ]
        database = SimpleNamespace(
            sql_engine=engine,
            target=RagTableTarget("configured_schema", "configured_chunks"),
        )
        publication = PostgresPublicationStore(database, collection_id="collection-a")

        with self.assertRaises(PublicationError):
            asyncio.run(publication._published_version_identity("source-a", "v1"))

    def test_DB_청크의_출처_메타데이터가_서로_다르면_게시_지문을_돌려주지_않는다(self) -> None:
        for field, value in (
            ("source_title", "Changed title"),
            ("publisher", "Changed publisher"),
            ("source_url", "https://example.invalid/changed"),
        ):
            with self.subTest(field=field):
                engine = _ReadEngine()
                engine.connection.published_identity_rows[1][field] = value
                database = SimpleNamespace(
                    sql_engine=engine,
                    target=RagTableTarget("configured_schema", "configured_chunks"),
                )
                publication = PostgresPublicationStore(database, collection_id="collection-a")

                with self.assertRaises(PublicationError):
                    asyncio.run(publication._published_version_identity("source-a", "v1"))

    def test_승인된_로컬_데이터베이스만_허용한다(self) -> None:
        accepted = validate_local_database_url(
            "postgresql+asyncpg://user@/starter_rag_integration?host=%2Ftmp"
        )
        self.assertEqual(accepted.database, "starter_rag_integration")

        for url in (
            "postgresql+asyncpg://user@/postgres?host=%2Ftmp",
            "postgresql+asyncpg://user@db.example.com/starter_rag_integration",
        ):
            with self.subTest(url=url), self.assertRaises(DatabaseConfigurationError):
                validate_local_database_url(url)

    def test_명시한_로컬_테스트_데이터베이스가_주소와_일치하고_원격은_거부한다(self) -> None:
        values = {
            "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/rag_isolated_test",
            "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
        }
        self.assertEqual(database_url_from_environment(values).database, "rag_isolated_test")
        values["RAG_DATABASE_URL"] = "postgresql+asyncpg://tester@127.0.0.1/postgres"
        with self.assertRaises(DatabaseConfigurationError):
            database_url_from_environment(values)
        values["RAG_DATABASE_URL"] = "postgresql+asyncpg://tester@db.example.com/rag_isolated_test"
        with self.assertRaises(DatabaseConfigurationError):
            database_url_from_environment(values)

    def test_잘못된_임베딩_출력은_색인_전에_거부한다(self) -> None:
        invalid_outputs = (
            (),
            ((0.1,) * 767,),
            ((float("nan"),) + (0.0,) * 767,),
        )
        chunk = ChunkRecord("chunk-1", "source-1", "v1", "sample text", "page 1")

        for vectors in invalid_outputs:
            with self.subTest(vector_count=len(vectors)):
                store = PGVectorStore(
                    object(), _ConfiguredEmbedding(vectors), collection_id="isolated-test"
                )
                with self.assertRaises(VectorIntegrityError):
                    asyncio.run(store.upsert((chunk,)))

    def test_검색_top_k_기본값과_범위를_유지한다(self) -> None:
        self.assertEqual(SearchRequest("query").top_k, 3)
        self.assertEqual(SearchRequest("query", top_k=10).top_k, 10)
        for top_k in (0, 11):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                SearchRequest("query", top_k=top_k)

    def test_미검증_자료의_기본_컬렉션_색인을_거부한다(self) -> None:
        store = PGVectorStore(None, _UnusedEmbedding(), collection_id=DEFAULT_COLLECTION_ID)  # type: ignore[arg-type]
        chunk = ChunkRecord("id", "source", "v1", "test text", "source location")

        async def operation() -> None:
            with self.assertRaises(VectorIntegrityError):
                await store.upsert((chunk,))

        asyncio.run(operation())


if __name__ == "__main__":
    unittest.main()
