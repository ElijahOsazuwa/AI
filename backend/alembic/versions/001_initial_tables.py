"""Initial tables for pr_events and reviews

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pr_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("sender", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("diff_url", sa.Text(), nullable=False),
        sa.Column("pr_title", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pr_events_repo_full_name", "pr_events", ["repo_full_name"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pr_event_id", sa.Integer(), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("pr_title", sa.String(length=500), nullable=True),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "done", "failed", name="reviewstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reviews_repo_full_name", "reviews", ["repo_full_name"])
    op.create_index("ix_reviews_pr_event_id", "reviews", ["pr_event_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_pr_event_id", table_name="reviews")
    op.drop_index("ix_reviews_repo_full_name", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_pr_events_repo_full_name", table_name="pr_events")
    op.drop_table("pr_events")
    # Clean up the enum type
    sa.Enum(name="reviewstatus").drop(op.get_bind(), checkfirst=True)
