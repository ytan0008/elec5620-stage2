"""Persist contextual learner-agent conversations.

Revision ID: a61d9c218e03
Revises: d4a1e6294b90
"""
from alembic import op
import sqlalchemy as sa

revision = "a61d9c218e03"
down_revision = "d4a1e6294b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("context", sa.String(30), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "context"),
    )
    op.create_index("ix_agent_conversations_user_id", "agent_conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_conversations_user_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
