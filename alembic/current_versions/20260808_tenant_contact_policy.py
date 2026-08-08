"""Add tenant-scoped lead contact requirement.

Revision ID: 20260808_tenant_contact_policy
Revises: 20260808_lead_import_registry
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_tenant_contact_policy"
down_revision = "20260808_lead_import_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "lead_contact_requirement",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "lead_contact_requirement")
