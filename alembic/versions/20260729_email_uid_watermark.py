"""Start Gmail ingestion at the tenant connection watermark.

Revision ID: 20260729_email_uid_watermark
Revises: 20260729_email_connections
"""
from alembic import op
import sqlalchemy as sa

revision = "20260729_email_uid_watermark"
down_revision = "20260729_email_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("tenant_email_connections")
    }
    if "imap_last_uid" not in columns:
        op.add_column(
            "tenant_email_connections",
            sa.Column("imap_last_uid", sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("tenant_email_connections")
    }
    if "imap_last_uid" in columns:
        op.drop_column("tenant_email_connections", "imap_last_uid")
