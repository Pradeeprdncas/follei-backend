"""Add category metadata and canonical section/entity provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20260722_category_aware"
down_revision = "20260722_lead_profile_data"
branch_labels = None
depends_on = None


def _columns(table):
    return {row["name"] for row in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    cols = _columns("documents")
    for name, column in (
        ("primary_category", sa.Column("primary_category", sa.String(40))),
        ("secondary_categories", sa.Column("secondary_categories", sa.JSON(), nullable=False, server_default="[]")),
        ("workspace_id", sa.Column("workspace_id", sa.Uuid())),
        ("processing_instructions", sa.Column("processing_instructions", sa.Text())),
        ("extractor_version", sa.Column("extractor_version", sa.String(64))),
        ("chunker_version", sa.Column("chunker_version", sa.String(64))),
    ):
        if name not in cols: op.add_column("documents", column)
    op.create_index("ix_documents_tenant_workspace_category", "documents", ["tenant_id", "workspace_id", "primary_category"], if_not_exists=True)
    if "document_sections" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("document_sections", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="SET NULL")), sa.Column("section_order", sa.Integer(), nullable=False), sa.Column("title", sa.String()), sa.Column("category", sa.String(40)), sa.Column("section_type", sa.String(64)), sa.Column("page_start", sa.Integer()), sa.Column("page_end", sa.Integer()), sa.Column("content", sa.Text()), sa.Column("summary", sa.Text()), sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(), nullable=False))
        op.create_index("ix_document_sections_tenant_document_order", "document_sections", ["tenant_id", "document_id", "section_order"])
    cols = _columns("document_chunks")
    for name, column in (("document_version_id", sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="SET NULL"))), ("section_id", sa.Column("section_id", sa.Uuid(), sa.ForeignKey("document_sections.id", ondelete="SET NULL"))), ("primary_category", sa.Column("primary_category", sa.String(40))), ("detected_category", sa.Column("detected_category", sa.String(40)))):
        if name not in cols: op.add_column("document_chunks", column)
    op.create_index("ix_chunks_tenant_category", "document_chunks", ["tenant_id", "primary_category"], if_not_exists=True)
    cols = _columns("entities")
    for name, column in (("workspace_id", sa.Column("workspace_id", sa.Uuid())), ("document_id", sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL"))), ("document_version_id", sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="SET NULL"))), ("category", sa.Column("category", sa.String(40))), ("schema_key", sa.Column("schema_key", sa.String(120))), ("schema_version", sa.Column("schema_version", sa.String(32))), ("data", sa.Column("data", sa.JSON(), nullable=False, server_default="{}")), ("status", sa.Column("status", sa.String(32), nullable=False, server_default="draft"))):
        if name not in cols: op.add_column("entities", column)
    op.create_index("ix_entities_tenant_document_category", "entities", ["tenant_id", "document_id", "category"], if_not_exists=True)


def downgrade():
    op.drop_table("document_sections")
    # Additive metadata columns are intentionally retained on downgrade to avoid
    # destroying production provenance during a rollback.
