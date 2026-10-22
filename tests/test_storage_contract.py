"""Pure validation checks for the local-only pgvector storage boundary."""

from __future__ import annotations

import asyncio
import unittest

from starter_rag.contracts.models import ChunkRecord, SearchRequest
from starter_rag.storage.database import DatabaseConfigurationError, validate_local_database_url
from starter_rag.storage.models import DEFAULT_COLLECTION_ID
from starter_rag.storage.vector_store import PGVectorStore, VectorIntegrityError, _validate_vectors


class _UnusedEmbedding:
    async def embed_query(self, text: str) -> tuple[float, ...]:
        return ()

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return ()


class StorageContractTests(unittest.TestCase):
    def test_only_approved_local_database_is_accepted(self) -> None:
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

    def test_vector_dimension_and_finite_values_are_required(self) -> None:
        with self.assertRaises(VectorIntegrityError):
            _validate_vectors(((0.1,) * 767,), 1)
        with self.assertRaises(VectorIntegrityError):
            _validate_vectors(((float("nan"),) + (0.0,) * 767,), 1)
        with self.assertRaises(VectorIntegrityError):
            _validate_vectors((), 1)

    def test_top_k_keeps_public_default_and_limits(self) -> None:
        self.assertEqual(SearchRequest("query").top_k, 3)
        self.assertEqual(SearchRequest("query", top_k=10).top_k, 10)
        for top_k in (0, 11):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                SearchRequest("query", top_k=top_k)

    def test_raw_upsert_cannot_put_unverified_rows_in_default_collection(self) -> None:
        store = PGVectorStore(None, _UnusedEmbedding(), collection_id=DEFAULT_COLLECTION_ID)  # type: ignore[arg-type]
        chunk = ChunkRecord("id", "source", "v1", "test text", "source location")

        async def operation() -> None:
            with self.assertRaises(VectorIntegrityError):
                await store.upsert((chunk,))

        asyncio.run(operation())


if __name__ == "__main__":
    unittest.main()
