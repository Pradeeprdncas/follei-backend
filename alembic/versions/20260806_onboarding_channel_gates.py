"""Add industry activation and verified non-email channel onboarding gates.

Revision ID: 20260806_channel_gates
Revises: 20260805_tenant_hubspot_sync
"""
from alembic import op
import sqlalchemy as sa


revision = "20260806_channel_gates"
down_revision = "20260805_tenant_hubspot_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("industry_pack_activated", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Existing tenants are activated only when both an industry and an instantiated workflow exist.
    op.execute(sa.text("""
        UPDATE tenants AS t
        SET industry_pack_activated = TRUE
        WHERE t.industry IS NOT NULL
          AND EXISTS (SELECT 1 FROM tenant_workflow_instances AS i WHERE i.tenant_id = t.id)
    """))

    op.create_table(
        "tenant_channel_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("identity", sa.String(255), nullable=False),
        sa.Column("provider_account_id", sa.String(255)),
        sa.Column("encrypted_account_sid", sa.Text()),
        sa.Column("encrypted_auth_token", sa.Text()),
        sa.Column("encrypted_api_key", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("campaign_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_verification"),
        sa.Column("verification_metadata", sa.JSON()),
        sa.Column("verified_at", sa.DateTime()),
        sa.Column("last_verified_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "channel", "provider", "identity", name="uq_tenant_channel_provider_identity"),
    )
    op.create_index("ix_tenant_channel_connections_tenant_id", "tenant_channel_connections", ["tenant_id"])
    op.create_index("ix_tenant_channel_connections_channel", "tenant_channel_connections", ["channel"])
    op.create_index("ix_tenant_channel_connections_provider", "tenant_channel_connections", ["provider"])
    op.create_index("ix_tenant_channel_connections_status", "tenant_channel_connections", ["status"])

    op.create_table(
        "channel_compliance_acknowledgements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("tenant_channel_connections.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("opt_in_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stop_help_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_channel_compliance_acknowledgements_tenant_id", "channel_compliance_acknowledgements", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_compliance_acknowledgements_tenant_id", table_name="channel_compliance_acknowledgements")
    op.drop_table("channel_compliance_acknowledgements")
    op.drop_index("ix_tenant_channel_connections_status", table_name="tenant_channel_connections")
    op.drop_index("ix_tenant_channel_connections_provider", table_name="tenant_channel_connections")
    op.drop_index("ix_tenant_channel_connections_channel", table_name="tenant_channel_connections")
    op.drop_index("ix_tenant_channel_connections_tenant_id", table_name="tenant_channel_connections")
    op.drop_table("tenant_channel_connections")
    op.drop_column("tenants", "industry_pack_activated")
