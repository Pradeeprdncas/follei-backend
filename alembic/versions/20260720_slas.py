"""Add tenant-scoped structured SLA records."""
from alembic import op
import sqlalchemy as sa

revision = "20260720_slas"
down_revision = "20260720_indexing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "slas" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "slas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("response_target_hours", sa.Integer(), nullable=True),
        sa.Column("resolution_target_hours", sa.Integer(), nullable=True),
        sa.Column("coverage", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_slas_tenant_id", "slas", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("slas")
