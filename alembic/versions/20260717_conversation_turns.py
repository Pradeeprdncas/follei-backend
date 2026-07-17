"""Add retry-safe conversation turn and structured-summary fields."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_conversation_turns"
down_revision = "20260716_fact_drafts"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    message_columns = _columns(bind, "conversation_messages")
    if "idempotency_key" not in message_columns:
        op.add_column("conversation_messages", sa.Column("idempotency_key", sa.String(length=160), nullable=True))
        op.create_index("ix_conversation_messages_tenant_idempotency", "conversation_messages", ["tenant_id", "idempotency_key"], unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"))
    summary_columns = _columns(bind, "conversation_summaries")
    if "source_message_count" not in summary_columns:
        op.add_column("conversation_summaries", sa.Column("source_message_count", sa.Integer(), nullable=True))
    if "status" not in summary_columns:
        op.add_column("conversation_summaries", sa.Column("status", sa.String(length=24), nullable=True, server_default="ready"))
        op.execute("UPDATE conversation_summaries SET status = 'ready' WHERE status IS NULL")
        op.alter_column("conversation_summaries", "status", nullable=False, server_default=None)
    if "metadata" not in summary_columns:
        op.add_column("conversation_summaries", sa.Column("metadata", sa.JSON(), nullable=True, server_default=sa.text("'{}'::json")))
        op.execute("UPDATE conversation_summaries SET metadata = '{}'::json WHERE metadata IS NULL")
        op.alter_column("conversation_summaries", "metadata", nullable=False, server_default=None)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("conversation_summaries")}
    if "ix_conversation_summaries_tenant_conversation_source" not in indexes:
        op.create_index("ix_conversation_summaries_tenant_conversation_source", "conversation_summaries", ["tenant_id", "conversation_id", "source_message_count"], unique=False)


def downgrade() -> None:
    pass
