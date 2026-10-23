# 담당: [D] | 책임: Backend 실행 진입점에 공개 RAG SearchPort를 제공한다.
# PRD: I09, I17
# 구현할 기능: 호출자가 소유한 PostgreSQL 엔진으로 검색 어댑터를 조립한다.
# 완료 기준: 테이블을 읽기 전용 검증하고 기존 SearchPort를 반환한다.
# 제한사항: DB 엔진을 닫거나 DDL·데이터 적재를 실행하지 않는다.
"""Backend 조립을 위한 공개 SearchPort 팩토리."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from starter_rag.contracts.ports import SearchPort
from starter_rag.embedding.model import EmbeddingGemma
from starter_rag.retrieval.search import PGVectorSearch
from starter_rag.storage.database import PostgresRagDatabase
from starter_rag.storage.models import RagTableTarget
from starter_rag.storage.vector_store import PGVectorStore


async def create_postgres_search_port(
    *,
    engine: AsyncEngine,
    schema_name: str,
    table_name: str,
    collection_id: str,
) -> SearchPort:
    """Build the published-only adapter over a caller-owned, pre-migrated table."""
    if not collection_id.strip():
        raise ValueError("collection_id must not be empty")
    database = PostgresRagDatabase.from_engine(
        engine,
        target=RagTableTarget(schema_name, table_name),
    )
    await database.validate_existing_table()
    embedding = EmbeddingGemma()
    vector_store = PGVectorStore(database, embedding, collection_id=collection_id)
    return PGVectorSearch(vector_store, embedding)
