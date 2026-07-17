"""Add tenant-scoped reviewable extracted business facts."""
from alembic import op
import sqlalchemy as sa

revision = "20260716_fact_drafts"
down_revision = "20260716_canonical_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "business_fact_drafts" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "business_fact_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("citation", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("approval_status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("reviewer", sa.String(length=120), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("published_record_type", sa.String(length=64), nullable=True),
        sa.Column("published_record_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    for name, columns in (
        ("ix_business_fact_drafts_tenant_id", ["tenant_id"]),
        ("ix_business_fact_drafts_document_id", ["document_id"]),
        ("ix_business_fact_drafts_chunk_id", ["chunk_id"]),
        ("ix_business_fact_drafts_fact_type", ["fact_type"]),
        ("ix_business_fact_drafts_approval_status", ["approval_status"]),
        ("ix_business_fact_drafts_tenant_status", ["tenant_id", "approval_status"]),
    ):
        op.create_index(name, "business_fact_drafts", columns, unique=False)


def downgrade() -> None:
    # Intentionally no-op: a review audit trail must not be deleted by downgrade.
    pass
