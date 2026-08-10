"""Restore tenant defaults retained by the pre-squash migration chain.

Revision ID: 20260810_tenant_defaults
Revises: 20260808_model_registry
"""
from alembic import op
import sqlalchemy as sa


revision = "20260810_tenant_defaults"
down_revision = "20260808_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tenants",
        "industry_pack_activated",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tenants",
        "industry_pack_activated",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
