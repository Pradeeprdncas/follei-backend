"""Add tenant-scoped Gmail OAuth credentials and single-use OAuth state.

Revision ID: 20260730_tenant_gmail_oauth
Revises: 20260729_email_uid_watermark
"""
from alembic import op
import sqlalchemy as sa

revision = "20260730_tenant_gmail_oauth"
down_revision = "20260729_email_uid_watermark"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("tenant_email_connections")
    additions = (
        ("auth_type", sa.Column("auth_type", sa.String(length=32), server_default="app_password", nullable=False)),
        ("encrypted_access_token", sa.Column("encrypted_access_token", sa.Text(), nullable=True)),
        ("encrypted_refresh_token", sa.Column("encrypted_refresh_token", sa.Text(), nullable=True)),
        ("access_token_expires_at", sa.Column("access_token_expires_at", sa.DateTime(), nullable=True)),
        ("oauth_scopes", sa.Column("oauth_scopes", sa.JSON(), nullable=True)),
        ("provider_account_id", sa.Column("provider_account_id", sa.String(length=255), nullable=True)),
        ("gmail_history_id", sa.Column("gmail_history_id", sa.String(length=64), nullable=True)),
        ("token_updated_at", sa.Column("token_updated_at", sa.DateTime(), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("tenant_email_connections", column)

    inspector = sa.inspect(op.get_bind())
    if "email_oauth_states" not in inspector.get_table_names():
        op.create_table(
            "email_oauth_states",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=24), server_default="gmail", nullable=False),
            sa.Column("state_hash", sa.String(length=64), nullable=False),
            sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
            sa.Column("expected_email", sa.String(length=320), nullable=True),
            sa.Column("sender_name", sa.String(length=160), nullable=True),
            sa.Column("auto_reply_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("allow_inbound_lead_creation", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("campaign_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("state_hash", name="uq_email_oauth_states_state_hash"),
        )
        op.create_index("ix_email_oauth_states_tenant_id", "email_oauth_states", ["tenant_id"])
        op.create_index("ix_email_oauth_states_user_id", "email_oauth_states", ["user_id"])
        op.create_index("ix_email_oauth_states_state_hash", "email_oauth_states", ["state_hash"], unique=True)
        op.create_index("ix_email_oauth_states_expires_at", "email_oauth_states", ["expires_at"])

    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("tenant_email_connections")}
    if "uq_active_gmail_mailbox" not in indexes:
        op.create_index(
            "uq_active_gmail_mailbox",
            "tenant_email_connections",
            ["provider", "email_address"],
            unique=True,
            postgresql_where=sa.text("provider = 'gmail' AND enabled = true"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("tenant_email_connections")}
    if "uq_active_gmail_mailbox" in indexes:
        op.drop_index("uq_active_gmail_mailbox", table_name="tenant_email_connections")
    if "email_oauth_states" in inspector.get_table_names():
        op.drop_table("email_oauth_states")
    columns = _columns("tenant_email_connections")
    for name in (
        "token_updated_at",
        "gmail_history_id",
        "provider_account_id",
        "oauth_scopes",
        "access_token_expires_at",
        "encrypted_refresh_token",
        "encrypted_access_token",
        "auth_type",
    ):
        if name in columns:
            op.drop_column("tenant_email_connections", name)
