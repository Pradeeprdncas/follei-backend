"""Add public Google identity-to-Workspace OAuth exchange records.

Revision ID: 20260811_google_auth
Revises: 20260810_adaptive_display
"""
from alembic import op
import sqlalchemy as sa


revision = "20260811_google_auth"
down_revision = "20260810_adaptive_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Identity OAuth begins before a Follei tenant/user exists. Authenticated
    # Workspace and HubSpot flows continue to write both columns.
    op.alter_column("integration_oauth_states", "tenant_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("integration_oauth_states", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_table(
        "oauth_login_exchanges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_oauth_login_exchanges_tenant_id", "oauth_login_exchanges", ["tenant_id"])
    op.create_index("ix_oauth_login_exchanges_user_id", "oauth_login_exchanges", ["user_id"])
    op.create_index("ix_oauth_login_exchanges_provider", "oauth_login_exchanges", ["provider"])
    op.create_index("ix_oauth_login_exchanges_code_hash", "oauth_login_exchanges", ["code_hash"], unique=True)
    op.create_index("ix_oauth_login_exchanges_expires_at", "oauth_login_exchanges", ["expires_at"])


def downgrade() -> None:
    for name in (
        "ix_oauth_login_exchanges_expires_at",
        "ix_oauth_login_exchanges_code_hash",
        "ix_oauth_login_exchanges_provider",
        "ix_oauth_login_exchanges_user_id",
        "ix_oauth_login_exchanges_tenant_id",
    ):
        op.drop_index(name, table_name="oauth_login_exchanges")
    op.drop_table("oauth_login_exchanges")
    # A downgrade cannot keep pre-account states because the old schema had no
    # representation for them.
    op.execute("DELETE FROM integration_oauth_states WHERE tenant_id IS NULL OR user_id IS NULL")
    op.alter_column("integration_oauth_states", "user_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("integration_oauth_states", "tenant_id", existing_type=sa.Uuid(), nullable=False)
