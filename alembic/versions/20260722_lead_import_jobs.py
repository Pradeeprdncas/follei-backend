"""Create durable lead-import jobs and extracted rows.

The lead import API persists a reviewable source record before it creates CRM
leads.  These tables were modelled but had no migration, which made the API
fail at its first insert on a freshly migrated database.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260722_lead_import_jobs"
down_revision = "20260722_category_aware"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "lead_import_jobs" not in tables:
        op.create_table(
            "lead_import_jobs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("public_id", sa.String(), nullable=True),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("file_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("uploaded_by", sa.String(), nullable=True),
            sa.Column("total_rows", sa.Integer(), nullable=True),
            sa.Column("valid_rows", sa.Integer(), nullable=True),
            sa.Column("duplicate_rows", sa.Integer(), nullable=True),
            sa.Column("invalid_rows", sa.Integer(), nullable=True),
            sa.Column("statistics", postgresql.JSONB(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_lead_import_jobs_tenant_id", "lead_import_jobs", ["tenant_id"])
        op.create_index("ix_lead_import_jobs_public_id", "lead_import_jobs", ["public_id"], unique=True)
        op.create_index("ix_lead_import_jobs_status", "lead_import_jobs", ["status"])
        op.create_index("ix_lead_import_jobs_created_at", "lead_import_jobs", ["created_at"])

    if "lead_import_rows" not in tables:
        op.create_table(
            "lead_import_rows",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("job_id", sa.Uuid(), sa.ForeignKey("lead_import_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("public_id", sa.String(), nullable=True),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_data", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("normalized_data", postgresql.JSONB(), nullable=True),
            sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("duplicate_of", sa.Uuid(), nullable=True),
            sa.Column("match_reason", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_lead_import_rows_job_id", "lead_import_rows", ["job_id"])
        op.create_index("ix_lead_import_rows_tenant_id", "lead_import_rows", ["tenant_id"])
        op.create_index("ix_lead_import_rows_public_id", "lead_import_rows", ["public_id"], unique=True)
        op.create_index("ix_lead_import_rows_duplicate", "lead_import_rows", ["duplicate"])
        op.create_index("ix_lead_import_rows_status", "lead_import_rows", ["status"])
        op.create_index("ix_lead_import_rows_lead_id", "lead_import_rows", ["lead_id"])


def downgrade() -> None:
    op.drop_table("lead_import_rows")
    op.drop_table("lead_import_jobs")
