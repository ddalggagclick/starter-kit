# 로컬 RAG SearchPort 옵트인 통합 테스트.

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path

from sqlalchemy import bindparam, text
from starter_rag.contracts.ports import SearchPort
from starter_rag.embedding.model import (
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_REVISION,
    EmbeddingGemma,
    EmbeddingInitializationError,
)
from starter_rag.evaluation.golden_set import (
    GoldenSetValidationError,
    evaluate_golden_set,
    load_golden_set,
    validate_chunk_mappings,
)
from starter_rag.retrieval.search import PGVectorSearch
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    PostgresRagDatabase,
    database_url_from_environment,
)
from starter_rag.storage.vector_store import PGVectorStore

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = REPO_ROOT / "rag/evaluation/golden_set_synthetic_ranking_v1.json"
INTEGRATION_ENABLED = os.environ.get("RUN_RAG_GOLDEN_SET_INTEGRATION") == "1"


@unittest.skipUnless(
    INTEGRATION_ENABLED,
    "set RUN_RAG_GOLDEN_SET_INTEGRATION=1 to run local DB/model integration",
)
class RagGoldenSetIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_실제_search_port로_현재_청크_라벨을_평가한다(self) -> None:
        try:
            database_url = database_url_from_environment()
        except DatabaseConfigurationError as exc:
            self.skipTest(str(exc))

        dataset = load_golden_set(GOLDEN_SET_PATH)
        if dataset.label_level != "chunk" or dataset.collection_id is None:
            self.skipTest("Golden Set has no declared chunk-level collection")
        if dataset.rag_publication_status != "confirmed_published":
            self.skipTest("Golden Set does not confirm its source collection is published")
        expected_is_synthetic = dataset.dataset_type == "synthetic_test"

        database = PostgresRagDatabase(database_url)
        try:
            async with database.sql_engine.connect() as connection, connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                table_name = (
                    await connection.execute(
                        text("SELECT to_regclass(:table_name)"),
                        {"table_name": "rag_test.chunks"},
                    )
                ).scalar_one()
                if table_name is None:
                    self.skipTest("rag_test.chunks table is not present")

                if expected_is_synthetic:
                    unexpected_chunk_count = (
                        await connection.execute(
                            text("""
                                SELECT count(*)
                                FROM rag_test.chunks
                                WHERE collection_id = :collection_id
                                  AND publication_state = :published_state
                                  AND is_synthetic IS DISTINCT FROM :is_synthetic
                            """),
                            {
                                "collection_id": dataset.collection_id,
                                "published_state": "published",
                                "is_synthetic": expected_is_synthetic,
                            },
                        )
                    ).scalar_one()
                    if unexpected_chunk_count:
                        self.fail(
                            "synthetic evaluation collection contains published non-synthetic "
                            "chunks that PGVectorSearch would include"
                        )

                matching_chunk_count = (
                    await connection.execute(
                        text("""
                                SELECT count(*)
                                FROM rag_test.chunks
                                WHERE collection_id = :collection_id
                                  AND publication_state = :published_state
                                  AND is_synthetic = :is_synthetic
                            """),
                        {
                            "collection_id": dataset.collection_id,
                            "published_state": "published",
                            "is_synthetic": expected_is_synthetic,
                        },
                    )
                ).scalar_one()
                if not matching_chunk_count:
                    self.skipTest(
                        "no published chunks matching the dataset type and collection exist"
                    )

                mapped_ids = {
                    label.evidence_id
                    for query in dataset.queries
                    for label in query.relevant_evidence
                    if label.location_mapping_status == "mapped" and label.evidence_id is not None
                }
                if not mapped_ids:
                    self.skipTest("Golden Set contains no verified evidence IDs")

                chunk_rows = (
                    (
                        await connection.execute(
                            text("""
                                SELECT chunk_id, source_id, version, source_title, publisher,
                                       source_url, publication_state, collection_id,
                                       is_synthetic, content, location,
                                       embedding_model_id, embedding_model_revision
                                FROM rag_test.chunks
                                WHERE chunk_id IN :chunk_ids
                                  AND collection_id = :collection_id
                                  AND publication_state = :published_state
                                  AND is_synthetic = :is_synthetic
                            """).bindparams(bindparam("chunk_ids", expanding=True)),
                            {
                                "chunk_ids": sorted(mapped_ids),
                                "collection_id": dataset.collection_id,
                                "published_state": "published",
                                "is_synthetic": expected_is_synthetic,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                records_by_id = {row["chunk_id"]: dict(row) for row in chunk_rows}
                try:
                    validate_chunk_mappings(dataset, records_by_id)
                except GoldenSetValidationError as exc:
                    self.fail(f"Golden Set chunk mapping validation failed: {exc}")

                complete_query_count = sum(
                    bool(query.relevant_evidence)
                    and all(
                        label.location_mapping_status == "mapped"
                        for label in query.relevant_evidence
                    )
                    for query in dataset.queries
                    if query.verification_status == "verified"
                )
                if not complete_query_count:
                    self.skipTest("no fully mapped answerable query is available for retrieval")

                snapshot_rows = (
                    (
                        await connection.execute(
                            text("""
                            SELECT chunk_id, source_id, version, content_sha256,
                                   embedding_model_id, embedding_model_revision
                            FROM rag_test.chunks
                            WHERE collection_id = :collection_id
                              AND publication_state = :published_state
                              AND is_synthetic = :is_synthetic
                            ORDER BY chunk_id
                        """),
                            {
                                "collection_id": dataset.collection_id,
                                "published_state": "published",
                                "is_synthetic": expected_is_synthetic,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                snapshot_payload = [dict(row) for row in snapshot_rows]
                if any(
                    row["embedding_model_id"] != EMBEDDING_MODEL_ID
                    or row["embedding_model_revision"] != EMBEDDING_MODEL_REVISION
                    for row in snapshot_payload
                ):
                    self.skipTest("indexed chunks use a different EmbeddingGemma model revision")
                snapshot_version = hashlib.sha256(
                    json.dumps(
                        snapshot_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8")
                ).hexdigest()
                if dataset.search_snapshot_version != snapshot_version:
                    self.fail("current published chunk snapshot does not match the Golden Set pin")

            embedding = EmbeddingGemma()
            search_port: SearchPort = PGVectorSearch(
                PGVectorStore(database, embedding, collection_id=dataset.collection_id),
                embedding,
                allow_synthetic=expected_is_synthetic,
            )
            try:
                summary = await evaluate_golden_set(
                    search_port,
                    dataset,
                    evaluation_mode="live",
                    run_metadata={
                        "search_implementation_version": "PGVectorSearch:starter-rag-0.1.0",
                        "search_snapshot_version": snapshot_version,
                        "embedding_model_id": EMBEDDING_MODEL_ID,
                        "embedding_model_revision": EMBEDDING_MODEL_REVISION,
                    },
                )
            except EmbeddingInitializationError as exc:
                self.skipTest(f"local EmbeddingGemma model is unavailable: {exc}")

            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            self.assertTrue(summary["retrieval_executed"])
            self.assertGreater(summary["evaluated_query_count"], 0)
        finally:
            await database.close()


if __name__ == "__main__":
    unittest.main()
