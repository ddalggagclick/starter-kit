# 담당: [D] | 책임: 승인된 RAG 로컬 PostgreSQL 연결과 pgvector 테이블 준비.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-3
# 제한사항: starter_rag_integration.rag_test.chunks만 생성·검증한다.
"""Local-only PostgreSQL configuration for the approved RAG integration table."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_postgres import PGEngine
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from starter_rag.storage.models import (
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    VECTOR_DIMENSION,
)


class DatabaseConfigurationError(ValueError):
    """The database URL is absent or does not target the approved local database."""


class DatabaseSchemaError(RuntimeError):
    """The approved vector table exists but does not satisfy the required shape."""


def validate_local_database_url(raw_url: str | URL) -> URL:
    """Accept only the approved local database; reject postgres and Supabase URLs."""
    try:
        url = raw_url if isinstance(raw_url, URL) else make_url(raw_url)
    except Exception as exc:
        raise DatabaseConfigurationError("RAG_DATABASE_URL is not a valid PostgreSQL URL") from exc
    if url.drivername != "postgresql+asyncpg" or url.database != DATABASE_NAME:
        raise DatabaseConfigurationError(
            f"RAG_DATABASE_URL must target local database {DATABASE_NAME} with asyncpg"
        )
    socket_host = url.query.get("host")
    local_host = url.host in {None, "localhost", "127.0.0.1", "::1"}
    local_socket = isinstance(socket_host, str) and socket_host.startswith("/")
    if not (local_host or local_socket):
        raise DatabaseConfigurationError(
            "RAG_DATABASE_URL must use a local host or Unix socket"
        )
    return url


def database_url_from_environment(
    environ: Mapping[str, str] | None = None,
) -> URL:
    import os

    values = os.environ if environ is None else environ
    raw_url = values.get("RAG_DATABASE_URL", "").strip()
    if not raw_url:
        raise DatabaseConfigurationError("RAG_DATABASE_URL is required")
    return validate_local_database_url(raw_url)


class PostgresRagDatabase:
    """Connection owner for explicit CLI setup, vector operations, and transactions."""

    def __init__(self, url: URL | str) -> None:
        self.url = validate_local_database_url(url)
        self.sql_engine: AsyncEngine = create_async_engine(self.url)
        # Share one async pool and event loop with direct transaction queries.
        self.pg_engine = PGEngine.from_engine(self.sql_engine)

    async def initialize(self) -> None:
        async with self.sql_engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
            result = await connection.execute(
                text("SELECT to_regclass(:qualified_name)"),
                {"qualified_name": f"{SCHEMA_NAME}.{TABLE_NAME}"},
            )
            table_exists = result.scalar_one() is not None

        if not table_exists:
            await self.pg_engine.ainit_vectorstore_table(
                TABLE_NAME,
                VECTOR_DIMENSION,
                schema_name=SCHEMA_NAME,
                content_column="content",
                embedding_column="embedding",
                id_column={"name": "chunk_id", "data_type": "TEXT", "nullable": False},
                metadata_columns=[
                    {"name": "source_id", "data_type": "TEXT", "nullable": False},
                    {"name": "version", "data_type": "TEXT", "nullable": False},
                    {
                        "name": "publication_state",
                        "data_type": "TEXT",
                        "nullable": False,
                    },
                    {"name": "collection_id", "data_type": "TEXT", "nullable": False},
                    {"name": "content_sha256", "data_type": "TEXT", "nullable": True},
                    {"name": "location", "data_type": "TEXT", "nullable": True},
                    {"name": "source_title", "data_type": "TEXT", "nullable": True},
                    {"name": "source_url", "data_type": "TEXT", "nullable": True},
                    {"name": "publisher", "data_type": "TEXT", "nullable": True},
                    {"name": "embedding_model_id", "data_type": "TEXT", "nullable": True},
                    {
                        "name": "embedding_model_revision",
                        "data_type": "TEXT",
                        "nullable": True,
                    },
                    {"name": "is_synthetic", "data_type": "BOOLEAN", "nullable": False},
                ],
                metadata_json_column="metadata",
                store_metadata=True,
            )

        await self._validate_table()
        async with self.sql_engine.begin() as connection:
            await connection.execute(
                text(
                    """DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'chunks_publication_state_check'
                          AND conrelid = 'rag_test.chunks'::regclass
                    ) THEN
                        ALTER TABLE rag_test.chunks
                        ADD CONSTRAINT chunks_publication_state_check
                        CHECK (publication_state IN ('staging', 'indexed', 'published', 'failed', 'retired'));
                    END IF;
                    END $$;"""
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS chunks_publication_scope_idx "
                    "ON rag_test.chunks (collection_id, publication_state, source_id, version)"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx "
                    "ON rag_test.chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )

    async def _validate_table(self) -> None:
        async with self.sql_engine.connect() as connection:
            result = await connection.execute(
                text(
                    """SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = :schema_name AND table_name = :table_name"""
                ),
                {"schema_name": SCHEMA_NAME, "table_name": TABLE_NAME},
            )
            columns = {row.column_name: (row.data_type, row.udt_name) for row in result}
            pk_result = await connection.execute(
                text(
                    """SELECT a.attname AS column_name
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = 'rag_test.chunks'::regclass AND i.indisprimary"""
                )
            )
            primary_key = tuple(row.column_name for row in pk_result)
            vector_result = await connection.execute(
                text(
                    """SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    WHERE a.attrelid = 'rag_test.chunks'::regclass AND a.attname = 'embedding'"""
                )
            )
            vector_type = vector_result.scalar_one_or_none()

        required = {
            "chunk_id",
            "content",
            "embedding",
            "source_id",
            "version",
            "publication_state",
            "collection_id",
            "content_sha256",
            "location",
            "source_title",
            "source_url",
            "publisher",
            "embedding_model_id",
            "embedding_model_revision",
            "is_synthetic",
            "metadata",
        }
        missing = required - columns.keys()
        if missing:
            raise DatabaseSchemaError(
                f"rag_test.chunks is missing required columns: {', '.join(sorted(missing))}"
            )
        if columns["chunk_id"][0] != "text" or primary_key != ("chunk_id",):
            raise DatabaseSchemaError("rag_test.chunks must use chunk_id TEXT as its primary key")
        if vector_type != f"vector({VECTOR_DIMENSION})":
            raise DatabaseSchemaError(
                f"rag_test.chunks.embedding must be vector({VECTOR_DIMENSION})"
            )
        text_columns = required - {"embedding", "is_synthetic", "metadata"}
        wrong_types = sorted(
            column
            for column in text_columns
            if columns[column][0] != "text"
        )
        if wrong_types:
            raise DatabaseSchemaError(
                f"rag_test.chunks columns must be TEXT: {', '.join(wrong_types)}"
            )
        if columns["is_synthetic"][0] != "boolean":
            raise DatabaseSchemaError("rag_test.chunks.is_synthetic must be BOOLEAN")
        if columns["metadata"][0] != "json":
            raise DatabaseSchemaError("rag_test.chunks.metadata must be JSON")

    async def table_counts(self, collection_id: str | None = None) -> dict[str, int]:
        query = "SELECT publication_state, count(*) AS row_count FROM rag_test.chunks"
        params: dict[str, Any] = {}
        if collection_id is not None:
            query += " WHERE collection_id = :collection_id"
            params["collection_id"] = collection_id
        query += " GROUP BY publication_state"
        async with self.sql_engine.connect() as connection:
            result = await connection.execute(text(query), params)
            return {row.publication_state: row.row_count for row in result}

    async def close(self) -> None:
        await self.sql_engine.dispose()
