"""Learner issue reports for the developer (teacher) console.

Revision ID: d5f81b2c9e47
Revises: c9d2e7a4f310
"""
from alembic import op
import sqlalchemy as sa

revision = "d5f81b2c9e47"
down_revision = "c9d2e7a4f310"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_issue_reports_user_id", "issue_reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_issue_reports_user_id", table_name="issue_reports")
    op.drop_table("issue_reports")
