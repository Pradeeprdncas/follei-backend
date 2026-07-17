"""Add canonical document lifecycle columns without modifying existing rows."""
from alembic import op
import sqlalchemy as sa

revision = "20260716_canonical_documents"
down_revision = "20260715_onboarding"
branch_labels = None
depends_on = None


def _columns(bind):
    return {column["name"] for column in sa.inspect(bind).get_columns("documents")}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    if "category" not in columns:
        op.add_column("documents", sa.Column("category", sa.String(length=40), nullable=True))
        op.create_index("ix_documents_category", "documents", ["category"], unique=False)
    if "version" not in columns:
        op.add_column("documents", sa.Column("version", sa.Integer(), nullable=True, server_default="1"))
        op.execute("UPDATE documents SET version = 1 WHERE version IS NULL")
        op.alter_column("documents", "version", nullable=False, server_default=None)
    if "previous_document_id" not in columns:
        op.add_column("documents", sa.Column("previous_document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True))
        op.create_index("ix_documents_previous_document_id", "documents", ["previous_document_id"], unique=False)
    if "sensitivity" not in columns:
        op.add_column("documents", sa.Column("sensitivity", sa.String(length=32), nullable=True, server_default="internal"))
        op.execute("UPDATE documents SET sensitivity = 'internal' WHERE sensitivity IS NULL")
        op.alter_column("documents", "sensitivity", nullable=False, server_default=None)
    if "uploaded_by" not in columns:
        op.add_column("documents", sa.Column("uploaded_by", sa.String(length=120), nullable=True))


def downgrade() -> None:
    # Intentionally no-op: removing lifecycle columns would be destructive.
    pass
