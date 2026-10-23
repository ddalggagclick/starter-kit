# 담당: [D] | 책임: 안내자료 버전의 게시 상태 전환.
# PRD: E6 / 스토리 6-2 / 태스크 6-2-3
# 구현할 기능: 검수·적재 결과에 따라 staging, indexed, published, failed, retired 상태를 관리한다.
# 완료 기준: 검수·게시된 버전만 검색 결과에 노출하고 URL 미상태도 보존한다.
# 제한사항: 게시 마커 변경과 벡터 저장 경계를 분리한다.
"""문서 버전의 게시 상태를 원자적으로 전환한다."""

from __future__ import annotations

from sqlalchemy import text

from starter_rag.contracts.models import DocumentVersion, SourceRef
from starter_rag.contracts.ports import PublicationPort
from starter_rag.storage.database import PostgresRagDatabase
from starter_rag.storage.models import DEFAULT_COLLECTION_ID


class PublicationError(RuntimeError):
    """문서 버전이 원자적 게시 조건을 만족하지 않는다."""


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
        self.table_name = database.target.qualified_name

    async def publish(self, source_id: str, version: str) -> DocumentVersion:
        async with self.database.sql_engine.begin() as connection:
            # 같은 출처·collection의 동시 게시 전환을 직렬화한다.
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"{self.collection_id}:{source_id}"},
            )
            result = await connection.execute(
                text(
                    f"""SELECT source_id, version, content_sha256, publication_state,
                    source_title, source_url, publisher, is_synthetic, location
                    FROM {self.table_name}
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
                    "publication requires valid source metadata and an optional HTTPS source URL"
                )
            if self.collection_id == DEFAULT_COLLECTION_ID and any(
                row["is_synthetic"] for row in rows
            ):
                raise PublicationError(
                    "synthetic test material cannot enter the published-guides collection"
                )

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
                    f"""UPDATE {self.table_name} SET publication_state = 'retired'
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
                    f"""UPDATE {self.table_name} SET publication_state = 'published'
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
    for row in rows:
        if not all(
            (
                row["source_id"],
                row["source_title"],
                row["publisher"],
                row["version"],
                row["location"],
            )
        ):
            return False
        try:
            SourceRef(
                source_id=row["source_id"],
                title=row["source_title"],
                url=row["source_url"],
                publisher=row["publisher"],
                version=row["version"],
            )
        except (TypeError, ValueError):
            return False
    return True


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
