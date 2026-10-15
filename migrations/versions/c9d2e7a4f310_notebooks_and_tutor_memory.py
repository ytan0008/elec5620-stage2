"""Learner notebooks (mistakes, words, grammar, sentences) and tutor memory.

Revision ID: c9d2e7a4f310
Revises: b7e3f0c41a52
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d2e7a4f310"
down_revision = "b7e3f0c41a52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notebook_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("key", sa.String(300), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("skill", sa.String(20), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("mastered", sa.Boolean(), nullable=False),
        sa.Column("review_level", sa.Integer(), nullable=False),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notebook_entries_user_id", "notebook_entries", ["user_id"])
    op.create_index("ix_notebook_entries_kind", "notebook_entries", ["kind"])
    op.create_index("ix_notebook_entries_key", "notebook_entries", ["key"])
    op.create_table(
        "learner_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learner_memories_user_id", "learner_memories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_learner_memories_user_id", table_name="learner_memories")
    op.drop_table("learner_memories")
    for name in ("key", "kind", "user_id"):
        op.drop_index(f"ix_notebook_entries_{name}", table_name="notebook_entries")
    op.drop_table("notebook_entries")
