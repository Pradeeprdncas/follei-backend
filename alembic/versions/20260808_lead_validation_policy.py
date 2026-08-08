"""Add durable lead verification state.

Revision ID: 20260808_lead_policy
Revises: 20260808_connector_oauth
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_lead_policy"
down_revision = "20260808_connector_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("verification_status", sa.String(24), nullable=False, server_default="pending"))
    op.create_index("ix_leads_verification_status", "leads", ["verification_status"])


def downgrade() -> None:
    op.drop_index("ix_leads_verification_status", table_name="leads")
    op.drop_column("leads", "verification_status")
