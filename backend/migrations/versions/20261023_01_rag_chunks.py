# 담당: [통합] | 책임: 승인된 RAG revision 구현과 ERD·운영 적용 승인을 분리한다.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-3; E7 / 스토리 7-3 / 태스크 7-3-3
# 구현할 기능: 외부에 설치된 pgvector 확장을 사용해 RAG 테이블과 인덱스를 만든다.
# 완료 기준: 16개 컬럼, 게시 상태 CHECK, B-tree·cosine HNSW 인덱스를 생성한다.
# 승인: 2026-10-24 통합관리자, revision 구현에 한정.
# Supabase DDL 실행 및 Source_v2 적재: 0건; 이 revision 구현만 완료.
# 사용자 제공 SQL 최종 대조: 16개 컬럼·자료형·NULL, PK/CHECK·3 인덱스가 revision과 일치(PASS).
# C 담당자 검증은 사용자 제공 SQL 증거 기준 완료; 직접 DB 조회는 하지 않음. ERD 문서 개정은 별도 지시 전 보류.
# 제한사항: pgvector 자동 설치·자료 적재·자동 stamp·파괴적 downgrade 금지.
"""Approved single-table RAG migration; application state is recorded separately from ERD approval.

Requires pgvector preinstalled in extensions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261023_01_rag_chunks"
down_revision = None
branch_labels = None
depends_on = None


class Vector768(sa.types.UserDefinedType):
    # 컬럼 선언에서 Supabase 확장 스키마를 명시한다.
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "extensions.vector(768)"


def upgrade() -> None:
    # 이미 존재하는 rag.chunks는 자동 덮어쓰기·stamp하지 않는다.
    op.execute(
        """DO $preflight$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_extension e
                JOIN pg_namespace n ON n.oid = e.extnamespace
                WHERE e.extname = 'vector' AND n.nspname = 'extensions'
            ) THEN
                RAISE EXCEPTION 'pgvector must be installed in extensions before rag migration';
            END IF;
            IF to_regclass('rag.chunks') IS NOT NULL THEN
                RAISE EXCEPTION 'rag.chunks already exists; stop and inspect before migration';
            END IF;
        END;
        $preflight$"""
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS rag")
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector768(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("publication_state", sa.Text(), nullable=False),
        sa.Column("collection_id", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("embedding_model_id", sa.Text(), nullable=True),
        sa.Column("embedding_model_revision", sa.Text(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.CheckConstraint(
            "publication_state IN ('staging', 'indexed', 'published', 'failed', 'retired')",
            name="chunks_publication_state_check",
        ),
        schema="rag",
    )
    op.create_index(
        "chunks_publication_scope_idx",
        "chunks",
        ["collection_id", "publication_state", "source_id", "version"],
        schema="rag",
    )
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw_idx "
        "ON rag.chunks USING hnsw (embedding extensions.vector_cosine_ops)"
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rag.chunks downgrade requires separate DB-owner approval")
