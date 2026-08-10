"""Persist adaptive category display and per-item review state.

Revision ID: 20260810_adaptive_display
Revises: 20260810_tenant_defaults
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260810_adaptive_display"
down_revision = "20260810_tenant_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "business_fact_drafts",
        sa.Column("item_review_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.execute(
        """
        UPDATE business_fact_drafts
        SET item_review_status = CASE
            WHEN approval_status = 'approved' THEN 'approved'
            WHEN approval_status IN ('rejected', 'superseded') THEN 'rejected'
            ELSE 'pending'
        END
        """
    )
    op.create_index(
        "ix_business_fact_drafts_item_review_status",
        "business_fact_drafts",
        ["item_review_status"],
    )

    op.add_column(
        "category_summaries",
        sa.Column("display_mode", sa.String(16), nullable=False, server_default="enumerable"),
    )
    op.add_column(
        "category_summaries",
        sa.Column(
            "breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "category_summaries",
        sa.Column(
            "sample_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "category_summaries",
        sa.Column("reviewed_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("category_summaries", "reviewed_count")
    op.drop_column("category_summaries", "sample_items")
    op.drop_column("category_summaries", "breakdown")
    op.drop_column("category_summaries", "display_mode")
    op.drop_index("ix_business_fact_drafts_item_review_status", table_name="business_fact_drafts")
    op.drop_column("business_fact_drafts", "item_review_status")
