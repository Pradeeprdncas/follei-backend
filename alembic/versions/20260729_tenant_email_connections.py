"""Tenant email connections and durable inbound-email identity.

Revision ID: 20260729_email_connections
Revises: 20260722_lead_import_jobs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260729_email_connections"
down_revision = "20260722_lead_import_jobs"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tenant_email_connections" not in inspector.get_table_names():
        op.create_table(
            "tenant_email_connections",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=24), nullable=False),
            sa.Column("email_address", sa.String(length=320), nullable=False),
            sa.Column("sender_name", sa.String(length=160), nullable=True),
            sa.Column("encrypted_api_key", sa.Text(), nullable=True),
            sa.Column("encrypted_app_password", sa.Text(), nullable=True),
            sa.Column("imap_host", sa.String(length=255), nullable=True),
            sa.Column("smtp_host", sa.String(length=255), nullable=True),
            sa.Column("smtp_port", sa.Integer(), nullable=True),
            sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("auto_reply_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("allow_inbound_lead_creation", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("campaign_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="configured", nullable=False),
            sa.Column("last_polled_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "provider", "email_address",
                name="uq_tenant_email_connection_provider_address",
            ),
        )
        op.create_index("ix_tenant_email_connections_tenant_id", "tenant_email_connections", ["tenant_id"])
        op.create_index("ix_tenant_email_connections_provider", "tenant_email_connections", ["provider"])
        op.create_index("ix_tenant_email_connections_email_address", "tenant_email_connections", ["email_address"])
        op.create_index("ix_tenant_email_connections_status", "tenant_email_connections", ["status"])

    inbound_columns = _columns("inbound_emails")
    if inbound_columns:
        additions = (
            ("conversation_id", sa.Column("conversation_id", sa.Uuid(), nullable=True)),
            ("provider_message_id", sa.Column("provider_message_id", sa.String(), nullable=True)),
            ("status", sa.Column("status", sa.String(), server_default="received", nullable=False)),
            ("metadata", sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)),
        )
        for name, column in additions:
            if name not in inbound_columns:
                op.add_column("inbound_emails", column)
        inspector = sa.inspect(op.get_bind())
        foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("inbound_emails")}
        if "fk_inbound_emails_conversation_id" not in foreign_keys:
            op.create_foreign_key(
                "fk_inbound_emails_conversation_id",
                "inbound_emails", "conversations",
                ["conversation_id"], ["id"], ondelete="SET NULL",
            )
        indexes = {index["name"] for index in inspector.get_indexes("inbound_emails")}
        if "ix_inbound_emails_conversation_id" not in indexes:
            op.create_index("ix_inbound_emails_conversation_id", "inbound_emails", ["conversation_id"])
        unique_names = {item.get("name") for item in inspector.get_unique_constraints("inbound_emails")}
        if "uq_inbound_email_tenant_provider_message" not in unique_names:
            op.create_unique_constraint(
                "uq_inbound_email_tenant_provider_message",
                "inbound_emails",
                ["tenant_id", "provider", "provider_message_id"],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "inbound_emails" in inspector.get_table_names():
        constraints = {item.get("name") for item in inspector.get_unique_constraints("inbound_emails")}
        if "uq_inbound_email_tenant_provider_message" in constraints:
            op.drop_constraint("uq_inbound_email_tenant_provider_message", "inbound_emails", type_="unique")
        indexes = {index["name"] for index in inspector.get_indexes("inbound_emails")}
        if "ix_inbound_emails_conversation_id" in indexes:
            op.drop_index("ix_inbound_emails_conversation_id", table_name="inbound_emails")
        foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("inbound_emails")}
        if "fk_inbound_emails_conversation_id" in foreign_keys:
            op.drop_constraint("fk_inbound_emails_conversation_id", "inbound_emails", type_="foreignkey")
        columns = _columns("inbound_emails")
        for name in ("metadata", "status", "provider_message_id", "conversation_id"):
            if name in columns:
                op.drop_column("inbound_emails", name)
    if "tenant_email_connections" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("tenant_email_connections")
