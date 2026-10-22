# 담당: [D] | 책임: PGVectorStore 저장과 벡터 검색.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-3
# 구현할 기능: 임베딩을 저장하고 게시된 문서 버전으로 검색 범위를 제한한다.
# 완료 기준: 검색 결과에 문서 버전, 공식 URL, 원문 위치가 연결된다.
# 제한사항: 법령 원문을 벡터 저장소에 저장하지 않는다.
"""Embedding-backed storage operations for the approved local pgvector table."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_postgres.v2.async_vectorstore import AsyncPGVectorStore
from sqlalchemy import bindparam, text

from starter_rag.contracts.models import ChunkRecord, DocumentVersion, SearchRequest
from starter_rag.contracts.ports import EmbeddingPort, VectorPort
from starter_rag.embedding.model import EMBEDDING_MODEL_ID, EMBEDDING_MODEL_REVISION
from starter_rag.storage.database import PostgresRagDatabase
from starter_rag.storage.models import (
    DEFAULT_COLLECTION_ID,
    SCHEMA_NAME,
    TABLE_NAME,
    VECTOR_DIMENSION,
)


class VectorStoreError(RuntimeError):
    """Base error raised by PostgreSQL vector persistence."""


class DocumentVersionConflictError(VectorStoreError):
    """The same source/version already exists with different chunks or provenance."""


class VectorIntegrityError(VectorStoreError, ValueError):
    """Chunk identity or embedding output does not match the storage contract."""


@dataclass(frozen=True)
class IndexOutcome:
    source_id: str
    version: str
    collection_id: str
    chunk_count: int
    state: str
    skipped: bool


@dataclass(frozen=True)
class DenseVectorHit:
    chunk_id: str
    text: str
    metadata: Mapping[str, Any]
    cosine_distance: float


_METADATA_COLUMNS = (
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
)


def _chunk_location(chunk: object) -> str:
    location = getattr(chunk, "location", None)
    if isinstance(location, str):
        return location
    locations = getattr(chunk, "locations", None)
    if locations:
        from dataclasses import asdict

        return json.dumps([asdict(value) for value in locations], ensure_ascii=False)
    raise VectorIntegrityError("chunk must preserve at least one original location")


def _chunk_metadata(
    *,
    source_id: str,
    version: str,
    collection_id: str,
    content_sha256: str | None,
    location: str,
    source_title: str | None,
    source_url: str | None,
    publisher: str | None,
    is_synthetic: bool,
    chunk: object,
    state: str = "staging",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "version": version,
        "publication_state": state,
        "collection_id": collection_id,
        "content_sha256": content_sha256,
        "location": location,
        "source_title": source_title,
        "source_url": source_url,
        "publisher": publisher,
        "embedding_model_id": EMBEDDING_MODEL_ID,
        "embedding_model_revision": EMBEDDING_MODEL_REVISION,
        "is_synthetic": is_synthetic,
        "chunk_kind": getattr(chunk, "kind", None),
        "element_ids": list(getattr(chunk, "element_ids", ())),
    }


def _validate_vectors(vectors: Sequence[Sequence[float]], expected: int) -> None:
    if len(vectors) != expected:
        raise VectorIntegrityError(f"expected {expected} embeddings; got {len(vectors)}")
    for vector in vectors:
        if len(vector) != VECTOR_DIMENSION:
            raise VectorIntegrityError(
                f"expected {VECTOR_DIMENSION}-dimension vector; got {len(vector)}"
            )
        if not all(math.isfinite(float(value)) for value in vector):
            raise VectorIntegrityError("embedding vector contains NaN or Infinity")


class PGVectorStore(VectorPort):
    """The approved PostgreSQL/pgvector implementation of ``VectorPort``."""

    def __init__(
        self,
        database: PostgresRagDatabase,
        embedding: EmbeddingPort,
        *,
        collection_id: str = DEFAULT_COLLECTION_ID,
    ) -> None:
        if not collection_id.strip():
            raise ValueError("collection_id must not be empty")
        self.database = database
        self.embedding = embedding
        self.collection_id = collection_id
        self._store: AsyncPGVectorStore | None = None

    async def _vectorstore(self) -> AsyncPGVectorStore:
        if self._store is None:
            self._store = await AsyncPGVectorStore.create(
                self.database.pg_engine,
                None,  # vectors are always generated explicitly through EmbeddingPort
                TABLE_NAME,
                schema_name=SCHEMA_NAME,
                content_column="content",
                embedding_column="embedding",
                metadata_columns=list(_METADATA_COLUMNS),
                id_column="chunk_id",
                metadata_json_column="metadata",
                k=3,
            )
        return self._store

    async def upsert(self, chunks: tuple[ChunkRecord, ...]) -> None:
        if not chunks:
            return
        if self.collection_id == DEFAULT_COLLECTION_ID:
            raise VectorIntegrityError(
                "raw VectorPort.upsert requires a non-production collection with explicit provenance"
            )
        self._validate_chunk_identity(chunks)
        texts = tuple(chunk.text for chunk in chunks)
        vectors = await self.embedding.embed_documents(texts)
        _validate_vectors(vectors, len(chunks))
        metadata = [
            _chunk_metadata(
                source_id=chunk.source_id,
                version=chunk.version,
                collection_id=self.collection_id,
                content_sha256=None,
                location=_chunk_location(chunk),
                source_title=None,
                source_url=None,
                publisher=None,
                is_synthetic=True,
                chunk=chunk,
            )
            for chunk in chunks
        ]
        await (await self._vectorstore()).aadd_embeddings(
            texts=list(texts),
            embeddings=[list(vector) for vector in vectors],
            metadatas=metadata,
            ids=[chunk.chunk_id for chunk in chunks],
        )

    async def index_document(
        self,
        document: DocumentVersion,
        chunks: tuple[object, ...],
        *,
        is_synthetic: bool = False,
    ) -> IndexOutcome:
        """Embed and stage a complete document version, then mark it indexed."""
        if is_synthetic and self.collection_id == DEFAULT_COLLECTION_ID:
            raise VectorIntegrityError(
                "synthetic test material requires a collection separate from published-guides"
            )
        if document.state != "staging":
            raise VectorIntegrityError("a new index operation must start in staging state")
        if len(chunks) != document.chunk_count or not chunks:
            raise VectorIntegrityError("document chunk count does not match index input")
        chunk_ids = tuple(str(getattr(chunk, "chunk_id", "")) for chunk in chunks)
        if any(not chunk_id for chunk_id in chunk_ids) or len(set(chunk_ids)) != len(chunk_ids):
            raise VectorIntegrityError("chunk IDs must be non-empty and unique")
        for chunk in chunks:
            if (
                getattr(chunk, "source_id", None) != document.source.source_id
                or getattr(chunk, "version", None) != document.source.version
                or not getattr(chunk, "text", "").strip()
            ):
                raise VectorIntegrityError("chunk identity or content differs from document version")

        existing = await self._version_rows(document.source.source_id, document.source.version)
        chunk_set = set(chunk_ids)
        if existing:
            existing_ids = {row["chunk_id"] for row in existing}
            if not existing_ids <= chunk_set:
                raise DocumentVersionConflictError(
                    "same source/version already contains a different chunk set"
                )
            chunk_by_id = {str(chunk.chunk_id): chunk for chunk in chunks}
            for row in existing:
                chunk = chunk_by_id[row["chunk_id"]]
                location = _chunk_location(chunk)
                if (
                    row["content_sha256"] != document.content_sha256
                    or row["content"] != chunk.text
                    or row["embedding_model_id"] != EMBEDDING_MODEL_ID
                    or row["embedding_model_revision"] != EMBEDDING_MODEL_REVISION
                    or row["location"] != location
                    or row["source_title"] != document.source.title
                    or row["source_url"] != document.source.url
                    or row["publisher"] != document.source.publisher
                    or row["is_synthetic"] != is_synthetic
                ):
                    raise DocumentVersionConflictError(
                        "same source/version was indexed with different content or provenance"
                    )
            all_chunks_present = existing_ids == chunk_set
            states = {row["publication_state"] for row in existing}
            if all_chunks_present and states == {"published"}:
                return IndexOutcome(
                    document.source.source_id,
                    document.source.version,
                    self.collection_id,
                    len(chunks),
                    "published",
                    True,
                )
            if all_chunks_present and states == {"indexed"}:
                return IndexOutcome(
                    document.source.source_id,
                    document.source.version,
                    self.collection_id,
                    len(chunks),
                    "indexed",
                    True,
                )
            if "published" in states or not states <= {"staging", "failed"}:
                raise DocumentVersionConflictError(
                    "only an exact published/indexed version or an unpublished retry can be reindexed"
                )

        collision_rows = await self._rows_for_chunk_ids(chunk_ids)
        for row in collision_rows:
            if (
                row["collection_id"] != self.collection_id
                or row["source_id"] != document.source.source_id
                or row["version"] != document.source.version
            ):
                raise DocumentVersionConflictError(
                    "chunk_id is already owned by another source, version, or collection"
                )

        texts = tuple(str(chunk.text) for chunk in chunks)
        vectors = await self.embedding.embed_documents(texts)
        _validate_vectors(vectors, len(chunks))
        metadatas = [
            _chunk_metadata(
                source_id=document.source.source_id,
                version=document.source.version,
                collection_id=self.collection_id,
                content_sha256=document.content_sha256,
                location=_chunk_location(chunk),
                source_title=document.source.title,
                source_url=document.source.url,
                publisher=document.source.publisher,
                is_synthetic=is_synthetic,
                chunk=chunk,
            )
            for chunk in chunks
        ]
        vectorstore = await self._vectorstore()
        try:
            await vectorstore.aadd_embeddings(
                texts=list(texts),
                embeddings=[list(vector) for vector in vectors],
                metadatas=metadatas,
                ids=list(chunk_ids),
            )
            async with self.database.sql_engine.begin() as connection:
                result = await connection.execute(
                    text(
                        """SELECT count(*) FROM rag_test.chunks
                        WHERE collection_id = :collection_id AND source_id = :source_id
                          AND version = :version AND chunk_id IN :chunk_ids"""
                    ).bindparams(bindparam("chunk_ids", expanding=True)),
                    {
                        "collection_id": self.collection_id,
                        "source_id": document.source.source_id,
                        "version": document.source.version,
                        "chunk_ids": list(chunk_ids),
                    },
                )
                if result.scalar_one() != len(chunk_ids):
                    raise VectorIntegrityError("database row count differs from expected chunks")
                await connection.execute(
                    text(
                        """UPDATE rag_test.chunks SET publication_state = 'indexed'
                        WHERE collection_id = :collection_id AND source_id = :source_id
                          AND version = :version AND publication_state = 'staging'"""
                    ),
                    {
                        "collection_id": self.collection_id,
                        "source_id": document.source.source_id,
                        "version": document.source.version,
                    },
                )
        except Exception:
            async with self.database.sql_engine.begin() as connection:
                await connection.execute(
                    text(
                        """UPDATE rag_test.chunks SET publication_state = 'failed'
                        WHERE collection_id = :collection_id AND source_id = :source_id
                          AND version = :version AND publication_state = 'staging'"""
                    ),
                    {
                        "collection_id": self.collection_id,
                        "source_id": document.source.source_id,
                        "version": document.source.version,
                    },
                )
            raise

        return IndexOutcome(
            document.source.source_id,
            document.source.version,
            self.collection_id,
            len(chunks),
            "indexed",
            False,
        )

    async def search_vectors(
        self,
        vector: tuple[float, ...],
        *,
        top_k: int,
        allow_synthetic: bool = False,
    ) -> tuple[DenseVectorHit, ...]:
        if not 1 <= top_k <= 10:
            raise ValueError("search top_k must be within 1..10")
        if allow_synthetic and self.collection_id == DEFAULT_COLLECTION_ID:
            raise ValueError("synthetic search is available only in an isolated test collection")
        _validate_vectors((vector,), 1)
        filters: dict[str, object] = {
            "collection_id": self.collection_id,
            "publication_state": "published",
        }
        if not allow_synthetic:
            filters["is_synthetic"] = False
        vectorstore = await self._vectorstore()
        rows = await vectorstore.asimilarity_search_with_score_by_vector(
            list(vector), k=top_k, filter=filters
        )
        hits: list[DenseVectorHit] = []
        for document, distance in rows:
            score = float(distance)
            if not math.isfinite(score):
                continue
            hits.append(
                DenseVectorHit(
                    chunk_id=str(document.id),
                    text=document.page_content,
                    metadata=dict(document.metadata),
                    cosine_distance=score,
                )
            )
        return tuple(sorted(hits, key=lambda hit: hit.cosine_distance))

    async def search_dense(self, request: SearchRequest):
        from starter_rag.retrieval.search import PGVectorSearch

        return await PGVectorSearch(self, self.embedding).search(request)

    async def get_by_id(self, chunk_id: str) -> ChunkRecord | None:
        async with self.database.sql_engine.connect() as connection:
            result = await connection.execute(
                text(
                    """SELECT chunk_id, source_id, version, content, location
                    FROM rag_test.chunks WHERE chunk_id = :chunk_id
                      AND collection_id = :collection_id"""
                ),
                {"chunk_id": chunk_id, "collection_id": self.collection_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            version=row["version"],
            text=row["content"],
            location=row["location"],
        )

    async def delete_version(self, source_id: str, version: str) -> None:
        """Delete only unpublished rows; published versions are protected."""
        async with self.database.sql_engine.begin() as connection:
            result = await connection.execute(
                text(
                    """DELETE FROM rag_test.chunks
                    WHERE collection_id = :collection_id AND source_id = :source_id
                      AND version = :version AND publication_state <> 'published'"""
                ),
                {
                    "collection_id": self.collection_id,
                    "source_id": source_id,
                    "version": version,
                },
            )
            if result.rowcount == 0:
                exists = await connection.execute(
                    text(
                        """SELECT 1 FROM rag_test.chunks
                        WHERE collection_id = :collection_id AND source_id = :source_id
                          AND version = :version AND publication_state = 'published' LIMIT 1"""
                    ),
                    {
                        "collection_id": self.collection_id,
                        "source_id": source_id,
                        "version": version,
                    },
                )
                if exists.first() is not None:
                    raise VectorStoreError("published document versions cannot be deleted")

    @staticmethod
    def _validate_chunk_identity(chunks: tuple[ChunkRecord, ...]) -> None:
        ids: set[str] = set()
        for chunk in chunks:
            if not all((chunk.chunk_id, chunk.source_id, chunk.version, chunk.text)):
                raise VectorIntegrityError("chunk identity and content are required")
            if chunk.chunk_id in ids:
                raise VectorIntegrityError("chunk IDs must be unique within an upsert")
            ids.add(chunk.chunk_id)

    async def _version_rows(self, source_id: str, version: str) -> list[Mapping[str, Any]]:
        async with self.database.sql_engine.connect() as connection:
            result = await connection.execute(
                text(
                    """SELECT chunk_id, content, content_sha256, publication_state,
                    embedding_model_id, embedding_model_revision, location, source_title,
                    source_url, publisher, is_synthetic
                    FROM rag_test.chunks WHERE collection_id = :collection_id
                      AND source_id = :source_id AND version = :version"""
                ),
                {
                    "collection_id": self.collection_id,
                    "source_id": source_id,
                    "version": version,
                },
            )
            return list(result.mappings().all())

    async def _rows_for_chunk_ids(self, chunk_ids: Sequence[str]) -> list[Mapping[str, Any]]:
        async with self.database.sql_engine.connect() as connection:
            result = await connection.execute(
                text(
                    """SELECT chunk_id, collection_id, source_id, version
                    FROM rag_test.chunks WHERE chunk_id IN :chunk_ids"""
                ).bindparams(bindparam("chunk_ids", expanding=True)),
                {"chunk_ids": list(chunk_ids)},
            )
            return list(result.mappings().all())
