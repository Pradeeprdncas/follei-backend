"""Add the canonical knowledge-ingestion control plane.

Revision ID: 20260808_ingestion_control
Revises: 20260806_channel_gates
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260808_ingestion_control"
down_revision = "20260806_channel_gates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "status" not in {column["name"] for column in inspector.get_columns("knowledge_sources")}:
        op.add_column("knowledge_sources", sa.Column("status", sa.String(24), nullable=False, server_default="active"))
        op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"])

    if "ingestion_runs" not in tables:
        op.create_table(
            "ingestion_runs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.Uuid(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for name, columns in (
            ("ix_ingestion_runs_tenant_id", ["tenant_id"]), ("ix_ingestion_runs_source_id", ["source_id"]),
            ("ix_ingestion_runs_status", ["status"]), ("ix_ingestion_runs_tenant_created", ["tenant_id", "created_at"]),
        ):
            op.create_index(name, "ingestion_runs", columns)

    if "ingestion_jobs" not in tables:
        op.create_table(
            "ingestion_jobs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("run_id", sa.Uuid(), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("job_type", sa.String(48), nullable=False),
            sa.Column("target", sa.Text()),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("last_error", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for name, columns in (
            ("ix_ingestion_jobs_tenant_id", ["tenant_id"]), ("ix_ingestion_jobs_run_id", ["run_id"]),
            ("ix_ingestion_jobs_job_type", ["job_type"]), ("ix_ingestion_jobs_status", ["status"]),
            ("ix_ingestion_jobs_run_type", ["run_id", "job_type"]),
        ):
            op.create_index(name, "ingestion_jobs", columns)

    if "category_summaries" not in tables:
        op.create_table(
            "category_summaries",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("category_key", sa.String(64), nullable=False),
            sa.Column("category_group", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="missing"),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary", sa.Text()),
            sa.Column("confidence", sa.Numeric(4, 3)),
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "category_key", name="uq_category_summary_tenant_key"),
        )
        op.create_index("ix_category_summaries_tenant_id", "category_summaries", ["tenant_id"])
        op.create_index("ix_category_summaries_tenant_status", "category_summaries", ["tenant_id", "status"])

    if "onboarding_confirmations" not in tables:
        op.create_table(
            "onboarding_confirmations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("requirement_key", sa.String(64), nullable=False),
            sa.Column("resolution", sa.String(32), nullable=False),
            sa.Column("note", sa.Text()),
            sa.Column("confirmed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("confirmed_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "requirement_key", name="uq_confirmation_tenant_requirement"),
        )
        op.create_index("ix_onboarding_confirmations_tenant_id", "onboarding_confirmations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_confirmations_tenant_id", table_name="onboarding_confirmations")
    op.drop_table("onboarding_confirmations")
    op.drop_index("ix_category_summaries_tenant_status", table_name="category_summaries")
    op.drop_index("ix_category_summaries_tenant_id", table_name="category_summaries")
    op.drop_table("category_summaries")
    for name in ("ix_ingestion_jobs_run_type", "ix_ingestion_jobs_status", "ix_ingestion_jobs_job_type", "ix_ingestion_jobs_run_id", "ix_ingestion_jobs_tenant_id"):
        op.drop_index(name, table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    for name in ("ix_ingestion_runs_tenant_created", "ix_ingestion_runs_status", "ix_ingestion_runs_source_id", "ix_ingestion_runs_tenant_id"):
        op.drop_index(name, table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index("ix_knowledge_sources_status", table_name="knowledge_sources")
    op.drop_column("knowledge_sources", "status")
