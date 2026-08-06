"""Add tenant-scoped HubSpot connections and three-store CRM sync records.

Revision ID: 20260805_tenant_hubspot_sync
Revises: 20260804_industry_workflow_runtime
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260805_tenant_hubspot_sync"
down_revision = "20260804_industry_workflow_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_crm_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("encrypted_access_token", sa.Text()),
        sa.Column("external_account_id", sa.String(255)),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("sync_cursor", postgresql.JSONB(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_crm_provider"),
    )
    op.create_index("ix_tenant_crm_connections_tenant_id", "tenant_crm_connections", ["tenant_id"])
    op.create_index("ix_tenant_crm_connections_status", "tenant_crm_connections", ["status"])
    op.create_table(
        "crm_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("tenant_crm_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("canonical_data", postgresql.JSONB(), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime()),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", "object_type", "external_id", name="uq_crm_record_external"),
    )
    for name, columns in (
        ("ix_crm_records_tenant_id", ["tenant_id"]),
        ("ix_crm_records_connection_id", ["connection_id"]),
        ("ix_crm_records_object_type", ["object_type"]),
        ("ix_crm_records_lead_id", ["lead_id"]),
        ("ix_crm_records_customer_id", ["customer_id"]),
        ("ix_crm_records_tenant_object", ["tenant_id", "object_type"]),
    ):
        op.create_index(name, "crm_records", columns)
    op.create_table(
        "crm_sync_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("tenant_crm_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_resources", postgresql.JSONB(), nullable=False),
        sa.Column("object_counts", postgresql.JSONB(), nullable=False),
        sa.Column("event_ids", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_index("ix_crm_sync_runs_tenant_id", "crm_sync_runs", ["tenant_id"])
    op.create_index("ix_crm_sync_runs_connection_id", "crm_sync_runs", ["connection_id"])
    op.create_index("ix_crm_sync_runs_status", "crm_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("crm_sync_runs")
    op.drop_table("crm_records")
    op.drop_table("tenant_crm_connections")
