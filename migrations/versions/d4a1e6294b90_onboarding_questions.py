"""Add onboarding, learner portraits and question bank.

Revision ID: d4a1e6294b90
Revises: c32c9f81d2aa
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a1e6294b90"
down_revision = "c32c9f81d2aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_onboarding_sessions_user_id", "onboarding_sessions", ["user_id"], unique=True)
    op.create_table(
        "learner_portraits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("result_packages.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learner_portraits_user_id", "learner_portraits", ["user_id"])
    op.create_table(
        "question_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("exam", sa.String(10), nullable=False),
        sa.Column("skill", sa.String(20), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("answer_key", sa.String(200), nullable=True),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("result_packages.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_question_items_exam", "question_items", ["exam"])
    op.create_index("ix_question_items_skill", "question_items", ["skill"])
    op.create_index("ix_question_items_user_id", "question_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_question_items_user_id", table_name="question_items")
    op.drop_index("ix_question_items_skill", table_name="question_items")
    op.drop_index("ix_question_items_exam", table_name="question_items")
    op.drop_table("question_items")
    op.drop_index("ix_learner_portraits_user_id", table_name="learner_portraits")
    op.drop_table("learner_portraits")
    op.drop_index("ix_onboarding_sessions_user_id", table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")
