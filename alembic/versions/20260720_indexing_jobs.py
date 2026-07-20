"""Add durable document indexing jobs."""
from alembic import op
import sqlalchemy as sa

revision = "20260720_indexing_jobs"
down_revision = "20260718_biz_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "indexing_jobs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "indexing_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("disposition", sa.String(24), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_indexing_jobs_tenant_id", "indexing_jobs", ["tenant_id"])
    op.create_index("ix_indexing_jobs_document_id", "indexing_jobs", ["document_id"])
    op.create_index("ix_indexing_jobs_status", "indexing_jobs", ["status"])
    op.create_index("ix_indexing_jobs_tenant_created", "indexing_jobs", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("indexing_jobs")
