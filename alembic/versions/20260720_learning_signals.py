"""Add learning_signals table backing app/models/learning_signal.py (System 6)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_learning_signals"
down_revision = "20260720_conversation_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "learning_signals" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "learning_signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("polarity", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("signal_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_learning_signals_tenant_id", "learning_signals", ["tenant_id"])
    op.create_index("ix_learning_signals_lead_id", "learning_signals", ["lead_id"])
    op.create_index("ix_learning_signals_conversation_id", "learning_signals", ["conversation_id"])
    op.create_index("ix_learning_signals_created_at", "learning_signals", ["created_at"])


def downgrade() -> None:
    op.drop_table("learning_signals")
