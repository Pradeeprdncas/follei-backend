"""Add generalized OAuth state, Google Workspace, and HubSpot refresh tokens.

Revision ID: 20260808_connector_oauth
Revises: 20260808_ingestion_control
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260808_connector_oauth"
down_revision = "20260808_ingestion_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_oauth_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for name, columns in (
        ("ix_integration_oauth_states_tenant_id", ["tenant_id"]),
        ("ix_integration_oauth_states_user_id", ["user_id"]),
        ("ix_integration_oauth_states_provider", ["provider"]),
        ("ix_integration_oauth_states_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "integration_oauth_states", columns)
    op.create_index("ix_integration_oauth_states_state_hash", "integration_oauth_states", ["state_hash"], unique=True)

    op.create_table(
        "google_workspace_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL")),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text()),
        sa.Column("access_token_expires_at", sa.DateTime()),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("enabled_resources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sync_cursors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider_account_id", name="uq_google_workspace_tenant_account"),
    )
    op.create_index("ix_google_workspace_connections_tenant_id", "google_workspace_connections", ["tenant_id"])
    op.create_index("ix_google_workspace_connections_status", "google_workspace_connections", ["status"])

    op.add_column("tenant_crm_connections", sa.Column("encrypted_refresh_token", sa.Text()))
    op.add_column("tenant_crm_connections", sa.Column("access_token_expires_at", sa.DateTime()))
    op.add_column("tenant_crm_connections", sa.Column("auth_type", sa.String(24), nullable=False, server_default="oauth"))


def downgrade() -> None:
    op.drop_column("tenant_crm_connections", "auth_type")
    op.drop_column("tenant_crm_connections", "access_token_expires_at")
    op.drop_column("tenant_crm_connections", "encrypted_refresh_token")
    op.drop_index("ix_google_workspace_connections_status", table_name="google_workspace_connections")
    op.drop_index("ix_google_workspace_connections_tenant_id", table_name="google_workspace_connections")
    op.drop_table("google_workspace_connections")
    for name in (
        "ix_integration_oauth_states_expires_at", "ix_integration_oauth_states_state_hash",
        "ix_integration_oauth_states_provider", "ix_integration_oauth_states_user_id",
        "ix_integration_oauth_states_tenant_id",
    ):
        op.drop_index(name, table_name="integration_oauth_states")
    op.drop_table("integration_oauth_states")
