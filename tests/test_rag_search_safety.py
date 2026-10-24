"""RAG 검색 필터·빈 결과·DB 실패의 공개 경계를 검증한다."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from starter_rag.composition import create_postgres_search_port
from starter_rag.contracts.models import SearchRequest, SearchResult
from starter_rag.retrieval.search import PGVectorSearch
from starter_rag.storage.database import (
    DatabaseConfigurationError,
    PostgresRagDatabase,
    validate_local_database_url,
)
from starter_rag.storage.models import RagTableTarget
from starter_rag.storage.vector_store import PGVectorStore


class _Embedding:
    async def embed_query(self, _: str) -> tuple[float, ...]:
        return (0.0,) * 768


class _SearchQuery:
    def __init__(self, rows=(), error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.call = None

    async def asimilarity_search_with_score_by_vector(self, vector, *, k, filter):
        self.call = (vector, k, filter)
        if self.error is not None:
            raise self.error
        return self.rows


def _database():
    return SimpleNamespace(
        pg_engine=object(),
        target=RagTableTarget("tenant_rag", "approved_chunks"),
    )


def _store(query: _SearchQuery | None = None, *, collection_id: str = "guides-v2"):
    store = PGVectorStore(_database(), _Embedding(), collection_id=collection_id)
    if query is not None:
        store._store = query
    return store


def test_검색쿼리에_컬렉션과_게시상태_필터를_전달한다():
    query = _SearchQuery(
        rows=(
            (
                SimpleNamespace(
                    id="guide-chunk-1",
                    page_content="검수 후 게시된 안내 자료",
                    metadata={
                        "collection_id": "guides-v2",
                        "publication_state": "published",
                        "is_synthetic": False,
                    },
                ),
                0.25,
            ),
        )
    )
    store = _store(query)

    hits = asyncio.run(store.search_vectors((0.0,) * 768, top_k=2))

    assert query.call == (
        [0.0] * 768,
        2,
        {
            "collection_id": "guides-v2",
            "publication_state": "published",
            "is_synthetic": False,
        },
    )
    assert [hit.chunk_id for hit in hits] == ["guide-chunk-1"]


def test_색인중과_폐기된_검색결과로는_근거를_생성하지_않는다():
    class HitStore:
        async def search_vectors(self, vector, *, top_k, allow_synthetic):
            return tuple(
                SimpleNamespace(
                    chunk_id=f"chunk-{state}",
                    text="검수된 안내 내용",
                    cosine_distance=0.25,
                    metadata={
                        "source_id": "guide-1",
                        "source_title": "안내 자료",
                        "source_url": "https://example.org/guide",
                        "publisher": "공식 기관",
                        "version": "v1",
                        "location": "page=1",
                        "publication_state": state,
                        "is_synthetic": False,
                    },
                )
                for state in ("published", "indexed", "retired")
            )

    result = asyncio.run(
        PGVectorSearch(HitStore(), _Embedding()).search(SearchRequest("안내 자료"))
    )

    assert [item.evidence_id for item in result.evidence] == ["chunk-published"]


def test_설정된_스키마와_테이블을_벡터저장소가_사용한다():
    async def operation():
        database = _database()
        store = PGVectorStore(database, _Embedding(), collection_id="guides-v2")
        created_store = _SearchQuery()
        with patch(
            "starter_rag.storage.vector_store.AsyncPGVectorStore.create",
            new_callable=AsyncMock,
            return_value=created_store,
        ) as create:
            actual = await store._vectorstore()

        assert actual is created_store
        args, kwargs = create.await_args
        assert args[0] is database.pg_engine
        assert args[1:3] == (None, "approved_chunks")
        assert kwargs["schema_name"] == "tenant_rag"

    asyncio.run(operation())


def test_공개_검색팩토리는_누락되거나_공백인_컬렉션식별자를_거부한다():
    with pytest.raises(TypeError):
        create_postgres_search_port(
            engine=object(), schema_name="tenant_rag", table_name="approved_chunks"
        )

    async def operation():
        with pytest.raises(ValueError, match="collection_id must not be empty"):
            await create_postgres_search_port(
                engine=object(),
                schema_name="tenant_rag",
                table_name="approved_chunks",
                collection_id=" ",
            )

    asyncio.run(operation())


@pytest.mark.parametrize(
    ("schema_name", "table_name"),
    (("rag_test; DROP TABLE chunks", "chunks"), ("rag_test", "chunks;--")),
)
def test_공개_검색팩토리는_잘못된_스키마와_테이블을_거부한다(schema_name, table_name):
    async def operation():
        with pytest.raises(ValueError):
            await create_postgres_search_port(
                engine=object(),
                schema_name=schema_name,
                table_name=table_name,
                collection_id="guides-v2",
            )

    asyncio.run(operation())


def test_검색결과가_없으면_공개_검색결과가_빈다():
    class EmptyStore:
        async def search_vectors(self, vector, *, top_k, allow_synthetic):
            return ()

    result = asyncio.run(
        PGVectorSearch(EmptyStore(), _Embedding()).search(SearchRequest("없는 안내 자료"))
    )

    assert result == SearchResult(evidence=())


def test_검색쿼리_오류를_정상적인_빈결과로_바꾸지_않는다():
    error = OperationalError("SELECT vector search", {}, OSError("query failed"))
    store = _store(_SearchQuery(error=error))

    async def operation():
        with pytest.raises(OperationalError) as raised:
            await store.search_vectors((0.0,) * 768, top_k=3)
        assert raised.value is error

    asyncio.run(operation())


def test_벡터저장소_생성오류를_정상적인_빈결과로_바꾸지_않는다():
    error = OperationalError("connect", {}, OSError("connection refused"))
    store = _store()

    async def operation():
        with (
            patch(
                "starter_rag.storage.vector_store.AsyncPGVectorStore.create",
                new_callable=AsyncMock,
                side_effect=error,
            ),
            pytest.raises(OperationalError) as raised,
        ):
            await store.search_vectors((0.0,) * 768, top_k=3)
        assert raised.value is error

    asyncio.run(operation())


def test_로컬_데이터베이스_연결오류에서_연결주소_비밀번호를_노출하지_않는다(caplog):
    password = "rag-validation-only-secret"
    database = PostgresRagDatabase(
        "postgresql+asyncpg://rag_test:rag-validation-only-secret@127.0.0.1:1/"
        "starter_rag_integration"
    )

    async def operation():
        try:
            with pytest.raises(ConnectionError) as raised:
                async with database.sql_engine.connect():
                    pass
            assert password not in str(raised.value)
            assert "postgresql+asyncpg://" not in str(raised.value)
        finally:
            await database.close()

    caplog.set_level(logging.DEBUG)
    asyncio.run(operation())
    assert password not in caplog.text


def test_잘못된_데이터베이스_연결주소의_오류메시지와_로그에_인증정보를_노출하지_않는다(caplog):
    password = "rag-validation-only-secret"
    url = (
        "postgresql+asyncpg://rag_test:rag-validation-only-secret@db.example.invalid/"
        "starter_rag_integration"
    )

    caplog.set_level(logging.DEBUG)
    with pytest.raises(DatabaseConfigurationError) as raised:
        validate_local_database_url(url)

    assert password not in str(raised.value)
    assert url not in str(raised.value)
    assert password not in caplog.text
