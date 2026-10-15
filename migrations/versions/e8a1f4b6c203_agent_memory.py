"""Per-agent working memory.

Revision ID: e8a1f4b6c203
Revises: d5f81b2c9e47
"""
from alembic import op
import sqlalchemy as sa

revision = "e8a1f4b6c203"
down_revision = "d5f81b2c9e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent", sa.String(40), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_memories_agent", "agent_memories", ["agent"])
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_memories_user_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_agent", table_name="agent_memories")
    op.drop_table("agent_memories")
