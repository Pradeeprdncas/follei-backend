"""Reconcile lead-import tables on databases stamped before the schema squash.

Revision ID: 20260808_lead_import_registry
Revises: 20260808_lead_policy
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260808_lead_import_registry"
down_revision = "20260808_lead_policy"
branch_labels = None
depends_on = None


def _ensure_indexes(table_name: str, definitions: list[tuple[str, list[str], bool]]) -> None:
    connection = op.get_bind()
    existing = {index["name"] for index in sa.inspect(connection).get_indexes(table_name)}
    for name, columns, unique in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if "lead_import_jobs" not in tables:
        op.create_table(
            "lead_import_jobs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("public_id", sa.String(), nullable=True),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("file_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("uploaded_by", sa.String(), nullable=True),
            sa.Column("total_rows", sa.Integer(), nullable=True),
            sa.Column("valid_rows", sa.Integer(), nullable=True),
            sa.Column("duplicate_rows", sa.Integer(), nullable=True),
            sa.Column("invalid_rows", sa.Integer(), nullable=True),
            sa.Column("statistics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_indexes("lead_import_jobs", [
        ("ix_lead_import_jobs_created_at", ["created_at"], False),
        ("ix_lead_import_jobs_id", ["id"], False),
        ("ix_lead_import_jobs_public_id", ["public_id"], True),
        ("ix_lead_import_jobs_status", ["status"], False),
        ("ix_lead_import_jobs_tenant_id", ["tenant_id"], False),
    ])

    tables = set(sa.inspect(connection).get_table_names())
    if "lead_import_rows" not in tables:
        op.create_table(
            "lead_import_rows",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("job_id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("public_id", sa.String(), nullable=True),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("normalized_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("duplicate", sa.Boolean(), nullable=True),
            sa.Column("duplicate_of", sa.Uuid(), nullable=True),
            sa.Column("match_reason", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("selected", sa.Boolean(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("lead_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["job_id"], ["lead_import_jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_indexes("lead_import_rows", [
        ("ix_lead_import_rows_duplicate", ["duplicate"], False),
        ("ix_lead_import_rows_id", ["id"], False),
        ("ix_lead_import_rows_job_id", ["job_id"], False),
        ("ix_lead_import_rows_lead_id", ["lead_id"], False),
        ("ix_lead_import_rows_public_id", ["public_id"], True),
        ("ix_lead_import_rows_status", ["status"], False),
        ("ix_lead_import_rows_tenant_id", ["tenant_id"], False),
    ])


def downgrade() -> None:
    # The squashed baseline owns these tables. Downgrading this reconciliation
    # marker must not remove schema or data that is valid at the baseline head.
    pass
