"""Add durable, tenant-scoped cross-store knowledge sync outbox."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_knowledge_sync_outbox"
down_revision = "20260717_conversation_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_sync_events" in inspector.get_table_names():
        return
    op.create_table(
        "knowledge_sync_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("deliveries", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_sync_events_tenant_id", "knowledge_sync_events", ["tenant_id"])
    op.create_index("ix_knowledge_sync_events_event_type", "knowledge_sync_events", ["event_type"])
    op.create_index("ix_knowledge_sync_events_status", "knowledge_sync_events", ["status"])
    op.create_index("ix_knowledge_sync_events_tenant_idempotency", "knowledge_sync_events", ["tenant_id", "idempotency_key"], unique=True)
    op.create_index("ix_knowledge_sync_events_status_created", "knowledge_sync_events", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("knowledge_sync_events")