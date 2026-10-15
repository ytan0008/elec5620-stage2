"""Structured exam content, live speaking sessions and avatar preference.

Revision ID: b7e3f0c41a52
Revises: a61d9c218e03
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e3f0c41a52"
down_revision = "a61d9c218e03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar", sa.String(20), nullable=False, server_default="witch"))
    with op.batch_alter_table("question_items") as batch:
        batch.add_column(sa.Column("content", sa.JSON(), nullable=True))
    op.create_table(
        "speaking_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("practice_id", sa.Integer(), sa.ForeignKey("practice_sessions.id"), nullable=True),
        sa.Column("mock_id", sa.Integer(), sa.ForeignKey("mock_examinations.id"), nullable=True),
        sa.Column("exam", sa.String(10), nullable=False),
        sa.Column("persona", sa.String(20), nullable=False),
        sa.Column("test", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("log", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_speaking_sessions_user_id", "speaking_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_speaking_sessions_user_id", table_name="speaking_sessions")
    op.drop_table("speaking_sessions")
    with op.batch_alter_table("question_items") as batch:
        batch.drop_column("content")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar")
