"""선택 실행하는 실제 모델·PostgreSQL 통합 검사 (T01-T08, T10).

RAG_DATABASE_URL은 승인된 로컬 starter_rag_integration DB만 가리켜야 하며,
임베딩·색인·게시·검색 성공 경로는 모의 처리하지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import text
from starter_rag.contracts.models import ChunkRecord, DocumentVersion, SearchRequest, SourceRef
from starter_rag.embedding.model import EMBEDDING_MODEL_ID, EMBEDDING_MODEL_REVISION, EmbeddingGemma
from starter_rag.retrieval.search import PGVectorSearch
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    PostgresRagDatabase,
    database_url_from_environment,
)
from starter_rag.storage.publication import PostgresPublicationStore, PublicationError
from starter_rag.storage.vector_store import (
    DocumentVersionConflictError,
    PGVectorStore,
    VectorIntegrityError,
)


class _WrongDimensionEmbedding:
    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (0.0,) * 767

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((0.0,) * 767 for _ in texts)


class PgVectorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_url = os.environ.get("RAG_DATABASE_URL", "").strip()
        if not raw_url:
            raise unittest.SkipTest(
                "RAG_DATABASE_URL is not set; real pgvector checks were not run"
            )
        try:
            cls.database_url = database_url_from_environment()
        except DatabaseConfigurationError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.run_id = uuid.uuid4().hex[:12]
        cls.embedding = EmbeddingGemma()
        cls.collection_id = f"rag-test-{cls.run_id}"
        cls.repo_root = Path(__file__).resolve().parents[1]

    def _run(self, operation):
        async def run():
            database = PostgresRagDatabase(self.database_url)
            try:
                await database.initialize()
                return await operation(database)
            finally:
                await database.close()

        return asyncio.run(run())

    def _source(self, source_key: str, version: str = "v1") -> SourceRef:
        return SourceRef(
            source_id=f"{self.run_id}-{source_key}",
            title=f"[합성 시험 자료] {source_key} 안내",
            url=f"https://example.invalid/rag-test/{self.run_id}/{source_key}/{version}",
            publisher="합성 통합 시험 자료",
            version=version,
        )

    def _chunk(self, source: SourceRef, text_value: str, suffix: str = "001") -> ChunkRecord:
        return ChunkRecord(
            chunk_id=f"{source.source_id}:{source.version}:chunk-{suffix}",
            source_id=source.source_id,
            version=source.version,
            text=text_value,
            location=json.dumps(
                {"status": "verified", "page_numbers": [1], "provenance": [{"page_no": 1}]},
                ensure_ascii=False,
            ),
        )

    def _document(self, source: SourceRef, *chunks: ChunkRecord) -> DocumentVersion:
        digest = hashlib.sha256("\n".join(chunk.text for chunk in chunks).encode()).hexdigest()
        return DocumentVersion(source, digest, "staging", len(chunks))

    def _count_document_rows(self, collection_id: str, source_id: str, version: str) -> int:
        async def operation(database):
            async with database.sql_engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """SELECT count(*) FROM rag_test.chunks
                        WHERE collection_id=:collection_id AND source_id=:source_id
                          AND version=:version"""
                    ),
                    {
                        "collection_id": collection_id,
                        "source_id": source_id,
                        "version": version,
                    },
                )
                return result.scalar_one()

        return self._run(operation)

    def test_실제_임베딩은_768차원을_반환한다(self) -> None:
        query_vector = asyncio.run(self.embedding.embed_query("How can users find sample records?"))
        document_vectors = asyncio.run(
            self.embedding.embed_documents(("Users can search for sample records.",))
        )
        self.assertEqual(len(query_vector), 768)
        self.assertEqual(len(document_vectors[0]), 768)
        self.assertTrue(
            all(math.isfinite(value) for value in (*query_vector, *document_vectors[0]))
        )
        print(f"T01 model={EMBEDDING_MODEL_ID}@{EMBEDDING_MODEL_REVISION} dimensions=768")

    def test_잘못된_벡터_차원은_삽입_전에_거부한다(self) -> None:
        source = self._source("dimension-reject")
        chunk = self._chunk(source, "dimension rejection fixture")

        async def operation(database):
            store = PGVectorStore(
                database, _WrongDimensionEmbedding(), collection_id=self.collection_id
            )
            with self.assertRaises(VectorIntegrityError):
                await store.index_document(
                    self._document(source, chunk), (chunk,), is_synthetic=True
                )
            async with database.sql_engine.connect() as connection:
                query = await connection.execute(
                    text("SELECT count(*) FROM rag_test.chunks WHERE chunk_id=:chunk_id"),
                    {"chunk_id": chunk.chunk_id},
                )
                self.assertEqual(query.scalar_one(), 0)

        self._run(operation)

    def test_데이터베이스_삽입은_메타데이터와_벡터_크기를_보존한다(self) -> None:
        source = self._source("database-insert")
        chunk = self._chunk(source, "A synthetic record search guide.")

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=self.collection_id)
            outcome = await store.index_document(
                self._document(source, chunk), (chunk,), is_synthetic=True
            )
            self.assertEqual(outcome.state, "indexed")
            async with database.sql_engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """SELECT chunk_id, source_id, version, location, publication_state,
                        vector_dims(embedding) AS dimensions
                        FROM rag_test.chunks WHERE chunk_id=:chunk_id"""
                    ),
                    {"chunk_id": chunk.chunk_id},
                )
                row = result.mappings().one()
            self.assertEqual(row["chunk_id"], chunk.chunk_id)
            self.assertEqual(row["source_id"], source.source_id)
            self.assertEqual(row["version"], source.version)
            self.assertEqual(row["location"], chunk.location)
            self.assertEqual(row["publication_state"], "indexed")
            self.assertEqual(row["dimensions"], 768)

        self._run(operation)

    def test_같은_버전_재실행은_멱등이고_게시_자료를_보호한다(self) -> None:
        source = self._source("idempotent")
        chunk = self._chunk(source, "A same-version guide to finding financial accounts.")

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=self.collection_id)
            document = self._document(source, chunk)
            first = await store.index_document(document, (chunk,), is_synthetic=True)
            published = await PostgresPublicationStore(
                database, collection_id=self.collection_id
            ).publish(source.source_id, source.version)
            second = await store.index_document(document, (chunk,), is_synthetic=True)
            self.assertFalse(first.skipped)
            self.assertEqual(published.state, "published")
            self.assertTrue(second.skipped)
            self.assertEqual(second.state, "published")
            async with database.sql_engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """SELECT count(*), count(DISTINCT chunk_id), min(publication_state)
                        FROM rag_test.chunks WHERE collection_id=:collection_id
                          AND source_id=:source_id AND version=:version"""
                    ),
                    {
                        "collection_id": self.collection_id,
                        "source_id": source.source_id,
                        "version": source.version,
                    },
                )
                count, unique_count, state = result.one()
            self.assertEqual((count, unique_count), (1, 1))
            self.assertEqual(state, "published")
            conflicting = self._chunk(source, "Changed text under the same version.")
            with self.assertRaises(DocumentVersionConflictError):
                await store.index_document(
                    self._document(source, conflicting), (conflicting,), is_synthetic=True
                )

        self._run(operation)

    def test_버전_변경은_분리되고_게시_전환은_원자적이다(self) -> None:
        old = self._source("version-switch", "v1")
        new = self._source("version-switch", "v2")
        old_chunk = self._chunk(old, "Version one account search guidance.")
        new_chunk = self._chunk(new, "Version two account search guidance.")

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=self.collection_id)
            publication = PostgresPublicationStore(database, collection_id=self.collection_id)
            await store.index_document(
                self._document(old, old_chunk), (old_chunk,), is_synthetic=True
            )
            await publication.publish(old.source_id, "v1")
            await store.index_document(
                self._document(new, new_chunk), (new_chunk,), is_synthetic=True
            )
            async with database.sql_engine.connect() as connection:
                before = await connection.execute(
                    text("SELECT publication_state FROM rag_test.chunks WHERE chunk_id=:chunk_id"),
                    {"chunk_id": old_chunk.chunk_id},
                )
                self.assertEqual(before.scalar_one(), "published")
            await publication.publish(new.source_id, "v2")
            async with database.sql_engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """SELECT chunk_id, version, publication_state FROM rag_test.chunks
                        WHERE source_id=:source_id ORDER BY version"""
                    ),
                    {"source_id": old.source_id},
                )
                rows = result.all()
            self.assertEqual({row.version for row in rows}, {"v1", "v2"})
            self.assertNotEqual(old_chunk.chunk_id, new_chunk.chunk_id)
            self.assertEqual({row.publication_state for row in rows}, {"retired", "published"})

        self._run(operation)

    def test_벡터검색_top_k는_관련_결과를_먼저_반환한다(self) -> None:
        collection = f"{self.collection_id}-ranking"
        relevant = self._source("ranking-relevant")
        unrelated = self._source("ranking-unrelated")
        relevant_chunk = self._chunk(
            relevant,
            "Users can locate sample records by name, category, and date in the searchable directory.",
        )
        unrelated_chunk = self._chunk(
            unrelated,
            "A basketball game is played by two teams on a court with a ball, hoop, and score.",
        )
        query = "How can users find records by name and date?"

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=collection)
            publication = PostgresPublicationStore(database, collection_id=collection)
            for source, chunk in ((relevant, relevant_chunk), (unrelated, unrelated_chunk)):
                await store.index_document(
                    self._document(source, chunk), (chunk,), is_synthetic=True
                )
                await publication.publish(source.source_id, source.version)
            search = PGVectorSearch(store, self.embedding, allow_synthetic=True)
            result = await search.search(SearchRequest(query))
            self.assertEqual(len(result.evidence), 2)
            self.assertEqual(result.evidence[0].evidence_id, relevant_chunk.chunk_id)
            self.assertGreaterEqual(result.evidence[0].score, result.evidence[1].score)

        self._run(operation)

    def test_게시_가능한_후보가_없으면_빈결과를_반환한다(self) -> None:
        collection = f"{self.collection_id}-empty"

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=collection)
            result = await PGVectorSearch(store, self.embedding, allow_synthetic=True).search(
                SearchRequest("no source exists in this isolated test collection")
            )
            self.assertEqual(result.evidence, ())

        self._run(operation)

    def test_게시_상태_자료만_검색할_수_있다(self) -> None:
        collection = f"{self.collection_id}-states"
        source_key = "state-transition"

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=collection)
            publication = PostgresPublicationStore(database, collection_id=collection)
            staging = self._source(f"{source_key}-staging")
            staging_chunk = self._chunk(staging, "state gate staging sentinel")
            await store.upsert((staging_chunk,))

            indexed = self._source(f"{source_key}-indexed")
            indexed_chunk = self._chunk(indexed, "state gate indexed sentinel")
            await store.index_document(
                self._document(indexed, indexed_chunk), (indexed_chunk,), is_synthetic=True
            )

            missing_url = SourceRef(
                source_id=f"{self.run_id}-{source_key}-missing-url",
                title="[합성 시험 자료] URL 누락 자료",
                url=None,
                publisher="합성 통합 시험 자료",
                version="v1",
            )
            missing_url_chunk = self._chunk(missing_url, "state gate missing URL sentinel")
            await store.index_document(
                self._document(missing_url, missing_url_chunk),
                (missing_url_chunk,),
                is_synthetic=True,
            )
            published_without_url = await publication.publish(
                missing_url.source_id, missing_url.version
            )
            self.assertEqual(published_without_url.state, "published")
            self.assertIsNone(published_without_url.source.url)

            failed = self._source(f"{source_key}-failed")
            failed_chunk = self._chunk(failed, "state gate failed sentinel")
            await store.index_document(
                self._document(failed, failed_chunk), (failed_chunk,), is_synthetic=True
            )
            async with database.sql_engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE rag_test.chunks SET publication_state='failed' WHERE chunk_id=:id"
                    ),
                    {"id": failed_chunk.chunk_id},
                )

            old = self._source(f"{source_key}-published", "v1")
            old_chunk = self._chunk(old, "state gate retired sentinel version one")
            await store.index_document(
                self._document(old, old_chunk), (old_chunk,), is_synthetic=True
            )
            await publication.publish(old.source_id, old.version)
            new = self._source(f"{source_key}-published", "v2")
            new_chunk = self._chunk(new, "state gate published sentinel version two")
            await store.index_document(
                self._document(new, new_chunk), (new_chunk,), is_synthetic=True
            )
            await publication.publish(new.source_id, new.version)

            result = await PGVectorSearch(store, self.embedding, allow_synthetic=True).search(
                SearchRequest("state gate sentinel")
            )
            returned_ids = {item.evidence_id for item in result.evidence}
            self.assertEqual(
                returned_ids,
                {new_chunk.chunk_id, missing_url_chunk.chunk_id},
            )
            evidence_by_id = {item.evidence_id: item for item in result.evidence}
            self.assertIsNone(evidence_by_id[missing_url_chunk.chunk_id].source.url)
            async with database.sql_engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        """SELECT chunk_id, publication_state FROM rag_test.chunks
                        WHERE collection_id=:collection_id"""
                    ),
                    {"collection_id": collection},
                )
                states = {row.publication_state for row in rows}
            self.assertEqual(states, {"staging", "indexed", "failed", "retired", "published"})

        self._run(operation)

    def test_설정한_컬렉션만_검색한다(self) -> None:
        collection = f"{self.collection_id}-isolation"
        foreign_collection = f"{collection}-foreign"
        source = self._source("collection-isolation-local")
        foreign_source = self._source("collection-isolation-foreign")
        text_value = "A published guide with the collection isolation marker."
        chunk = self._chunk(source, text_value)
        foreign_chunk = self._chunk(foreign_source, text_value)

        async def operation(database):
            publication = PostgresPublicationStore(database, collection_id=collection)
            foreign_publication = PostgresPublicationStore(
                database, collection_id=foreign_collection
            )
            store = PGVectorStore(database, self.embedding, collection_id=collection)
            foreign_store = PGVectorStore(
                database, self.embedding, collection_id=foreign_collection
            )
            await store.index_document(self._document(source, chunk), (chunk,), is_synthetic=True)
            await publication.publish(source.source_id, source.version)
            await foreign_store.index_document(
                self._document(foreign_source, foreign_chunk),
                (foreign_chunk,),
                is_synthetic=True,
            )
            await foreign_publication.publish(foreign_source.source_id, foreign_source.version)

            self.assertEqual(await publication.published_chunk_count(source.source_id, "v1"), 1)
            identity = await publication._published_version_identity(source.source_id, "v1")
            self.assertIsNotNone(identity)
            self.assertEqual(identity.chunk_count, 1)
            self.assertEqual(
                identity.content_sha256, hashlib.sha256(text_value.encode()).hexdigest()
            )
            self.assertIsNone(identity.review_sha256)
            self.assertEqual(
                await store._published_chunk_ids([chunk.chunk_id, foreign_chunk.chunk_id]),
                {chunk.chunk_id},
            )
            self.assertEqual(
                await foreign_store._published_chunk_ids([chunk.chunk_id, foreign_chunk.chunk_id]),
                {foreign_chunk.chunk_id},
            )

            search = PGVectorSearch(store, self.embedding, allow_synthetic=True)
            result = await search.search(SearchRequest("collection isolation marker"))
            self.assertEqual(
                {item.evidence_id for item in result.evidence},
                {chunk.chunk_id},
            )

            mismatched = PGVectorStore(
                database, self.embedding, collection_id=f"{collection}-misspelled"
            )
            mismatch_result = await PGVectorSearch(
                mismatched, self.embedding, allow_synthetic=True
            ).search(SearchRequest("collection isolation marker"))
            self.assertEqual(mismatch_result.evidence, ())

        self._run(operation)

    def test_실제_모델과_DB로_CLI_재색인_게시_검색을_검증한다(self) -> None:
        try:
            import openpyxl
        except ImportError as exc:
            self.fail(f"openpyxl must be available for the real CLI workbook path: {exc}")
        collection = f"{self.collection_id}-cli"
        source_id = f"{self.run_id}-cli-source"
        version = "cli-v1"
        tokenizer_path = "google/embeddinggemma-2"
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(self.repo_root / "rag"),
                "RAG_CHUNKING_PROVIDER": "ollama",
                "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
                "RAG_CHUNKING_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            }
        )
        cli_entrypoint = Path(sys.executable).with_name("starter-rag")
        self.assertTrue(cli_entrypoint.exists(), "starter-rag console entrypoint must be installed")

        def command(*args: str) -> dict[str, object]:
            result = subprocess.run(
                [str(cli_entrypoint), *args],
                cwd=self.repo_root,
                env=environment,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=f"{args[0]} stderr: {result.stderr}")
            return json.loads(result.stdout)

        with tempfile.TemporaryDirectory(prefix="rag-cli-real-") as temp_dir:
            input_path = Path(temp_dir) / "synthetic_guide.xlsx"
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = "Guide"
            worksheet.append(("Topic", "Details"))
            worksheet.append(
                (
                    "Directory search",
                    "Users can search the directory for records by name, category, and date.",
                )
            )
            workbook.save(input_path)
            workbook.close()

            setup = command("db-init")
            self.assertEqual(
                setup["database"],
                os.environ.get("RAG_LOCAL_DATABASE_NAME", "starter_rag_integration"),
            )
            base_args = (
                "index",
                str(input_path),
                "--tokenizer-path",
                tokenizer_path,
                "--source-id",
                source_id,
                "--version",
                version,
                "--source-title",
                "[합성 시험 자료] CLI directory guide",
                "--source-url",
                "https://example.invalid/rag-cli-test/guide",
                "--publisher",
                "합성 CLI 통합 테스트",
                "--collection-id",
                collection,
                "--synthetic",
            )
            first = command(*base_args)
            rows_after_first = self._count_document_rows(collection, source_id, version)
            second = command(*base_args)
            rows_after_second = self._count_document_rows(collection, source_id, version)
            self.assertGreater(first["chunkCount"], 0)
            self.assertFalse(first["skippedExistingVersion"])
            self.assertTrue(second["skippedExistingVersion"])
            self.assertEqual(rows_after_first, first["chunkCount"])
            self.assertEqual(rows_after_second, rows_after_first)
            publication = command(
                "publish",
                "--source-id",
                source_id,
                "--version",
                version,
                "--collection-id",
                collection,
            )
            self.assertEqual(publication["state"], "published")
            search_result = command(
                "search",
                "directory search for records",
                "--top-k",
                "3",
                "--collection-id",
                collection,
                "--allow-synthetic",
            )
            self.assertGreaterEqual(len(search_result["evidence"]), 1)
            self.assertEqual(search_result["evidence"][0]["source"]["source_id"], source_id)
            print(
                "T10 cli=real model+postgres chunks="
                f"{first['chunkCount']} rows={rows_after_first}->{rows_after_second} "
                f"rerun_skipped={second['skippedExistingVersion']}"
            )

    def test_승인_해시가_일치하지_않는_색인_자료는_게시할_수_없다(self) -> None:
        source = self._source("reviewed-publication")
        chunk = self._chunk(source, "A reviewed source with an approval fingerprint.")
        document = self._document(source, chunk)
        review_hash = hashlib.sha256(b"review snapshot").hexdigest()

        async def operation(database):
            store = PGVectorStore(database, self.embedding, collection_id=self.collection_id)
            publication = PostgresPublicationStore(database, collection_id=self.collection_id)
            await store.index_document(
                document,
                (chunk,),
                is_synthetic=True,
                review_sha256=review_hash,
            )

            with self.assertRaises(PublicationError):
                await publication.publish(source.source_id, source.version)
            with self.assertRaises(PublicationError):
                await publication.publish_with_outcome(
                    source.source_id,
                    source.version,
                    allow_version_replacement=False,
                    review_sha256="different-review",
                    expected_source_sha256=document.content_sha256,
                )

            published = await publication.publish_with_outcome(
                source.source_id,
                source.version,
                allow_version_replacement=False,
                review_sha256=review_hash,
                expected_source_sha256=document.content_sha256,
            )
            self.assertEqual(published.document.state, "published")

        self._run(operation)


if __name__ == "__main__":
    unittest.main()
