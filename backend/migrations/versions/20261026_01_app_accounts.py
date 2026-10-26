# 담당: [통합] | 책임: 계정·인증 세션·1회용 링크·A17 서버 체크리스트 테이블(app 스키마).
# PRD: E5 / 5-1-3, 5-4-2; E4 / 4-6-2, 4-5-2
# 구현할 기능: 회원 기능과 A17을 메모리 저장소에서 Supabase PostgreSQL로 옮길 테이블을 만든다.
# 완료 기준: 비밀번호·토큰은 해시만 저장하고, 사용자 삭제 시 관련 자료가 함께 지워진다.
# 승인: 2026-10-26 DB 승인 담당(김현주) 테이블 설계 승인, revision 구현에 한정. 운영 적용은 명시적 실행.
# 제한사항: AI 질문·답변 원문을 저장하는 테이블을 만들지 않는다(4-5-2). 파괴적 downgrade 금지.
"""app 스키마 계정 테이블. rag.chunks(20261023_01) 다음 revision."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261026_01_app_accounts"
down_revision = "20261023_01_rag_chunks"
branch_labels = None
depends_on = None

SCHEMA = "app"


def _user_fk() -> sa.ForeignKey:
    return sa.ForeignKey(f"{SCHEMA}.users.user_id", ondelete="CASCADE")


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    op.create_table(
        "users",
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("token_hash", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, _user_fk(), nullable=False),
        sa.Column("family_id", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.create_index("refresh_sessions_user_idx", "refresh_sessions", ["user_id"], schema=SCHEMA)
    op.create_index("refresh_sessions_family_idx", "refresh_sessions", ["family_id"], schema=SCHEMA)
    op.create_table(
        "one_time_tokens",
        sa.Column("token_hash", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("user_id", sa.Text, _user_fk(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "kind IN ('email_verify', 'password_reset')", name="one_time_tokens_kind_check"
        ),
        schema=SCHEMA,
    )
    op.create_index("one_time_tokens_user_idx", "one_time_tokens", ["user_id"], schema=SCHEMA)
    op.create_table(
        "server_checklists",
        sa.Column("user_id", sa.Text, _user_fk(), primary_key=True),
        sa.Column("item_states", JSONB, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    raise RuntimeError("Destructive app schema downgrade requires separate DB-owner approval")
