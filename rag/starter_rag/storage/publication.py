# 담당: [D] | 책임: 안내자료 버전의 게시 상태 전환.
# PRD: E6 / 스토리 6-2 / 태스크 6-2-3
# 구현할 기능: 검수·적재 결과에 따라 staging, indexed, published, failed, retired 상태를 관리한다.
# 완료 기준: 검수·게시된 버전만 검색 결과에 노출된다.
# 제한사항: 게시 마커 변경과 벡터 저장 경계를 분리한다.
"""Atomic publication state transitions for document versions."""

from __future__ import annotations

from sqlalchemy import text

from starter_rag.contracts.models import DocumentVersion, SourceRef
from starter_rag.contracts.ports import PublicationPort
from starter_rag.storage.database import PostgresRagDatabase
from starter_rag.storage.models import DEFAULT_COLLECTION_ID


class PublicationError(RuntimeError):
    """A document version is not eligible for atomic publication."""


class PostgresPublicationStore(PublicationPort):
    def __init__(
        self,
        database: PostgresRagDatabase,
        *,
        collection_id: str = DEFAULT_COLLECTION_ID,
    ) -> None:
        if not collection_id.strip():
            raise ValueError("collection_id must not be empty")
        self.database = database
        self.collection_id = collection_id

    async def publish(self, source_id: str, version: str) -> DocumentVersion:
        async with self.database.sql_engine.begin() as connection:
            # Serialize competing publication switches for this source/collection.
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"{self.collection_id}:{source_id}"},
            )
            result = await connection.execute(
                text(
                    """SELECT source_id, version, content_sha256, publication_state,
                    source_title, source_url, publisher, is_synthetic, location
                    FROM rag_test.chunks
                    WHERE collection_id = :collection_id AND source_id = :source_id
                      AND version = :version
                    FOR UPDATE"""
                ),
                {
                    "collection_id": self.collection_id,
                    "source_id": source_id,
                    "version": version,
                },
            )
            rows = list(result.mappings().all())
            if not rows:
                raise PublicationError("document version has no indexed chunks")
            states = {row["publication_state"] for row in rows}
            if states == {"published"}:
                return _document_version(rows[0], "published", len(rows))
            if states != {"indexed"}:
                raise PublicationError("only a complete indexed version can be published")
            if not _has_publishable_provenance(rows):
                raise PublicationError(
                    "publication requires an HTTPS source URL, title, publisher, version, and location"
                )
            if self.collection_id == DEFAULT_COLLECTION_ID and any(
                row["is_synthetic"] for row in rows
            ):
                raise PublicationError("synthetic test material cannot enter the published-guides collection")

            reference = rows[0]
            inconsistent = any(
                row["content_sha256"] != reference["content_sha256"]
                or row["source_title"] != reference["source_title"]
                or row["source_url"] != reference["source_url"]
                or row["publisher"] != reference["publisher"]
                or row["is_synthetic"] != reference["is_synthetic"]
                for row in rows
            )
            if inconsistent:
                raise PublicationError("document version metadata is inconsistent across chunks")

            await connection.execute(
                text(
                    """UPDATE rag_test.chunks SET publication_state = 'retired'
                    WHERE collection_id = :collection_id AND source_id = :source_id
                      AND publication_state = 'published' AND version <> :version"""
                ),
                {
                    "collection_id": self.collection_id,
                    "source_id": source_id,
                    "version": version,
                },
            )
            updated = await connection.execute(
                text(
                    """UPDATE rag_test.chunks SET publication_state = 'published'
                    WHERE collection_id = :collection_id AND source_id = :source_id
                      AND version = :version AND publication_state = 'indexed'"""
                ),
                {
                    "collection_id": self.collection_id,
                    "source_id": source_id,
                    "version": version,
                },
            )
            if updated.rowcount != len(rows):
                raise PublicationError("publication state changed during transition")
            return _document_version(reference, "published", len(rows))


def _has_publishable_provenance(rows) -> bool:
    return all(
        bool(row["source_title"] and row["publisher"] and row["version"] and row["location"])
        and isinstance(row["source_url"], str)
        and row["source_url"].startswith("https://")
        for row in rows
    )


def _document_version(row, state: str, chunk_count: int) -> DocumentVersion:
    return DocumentVersion(
        source=SourceRef(
            source_id=row["source_id"],
            title=row["source_title"],
            url=row["source_url"],
            publisher=row["publisher"],
            version=row["version"],
        ),
        content_sha256=row["content_sha256"],
        state=state,  # type: ignore[arg-type]
        chunk_count=chunk_count,
    )
