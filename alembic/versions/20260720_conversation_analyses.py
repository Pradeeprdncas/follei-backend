"""Add conversation_analyses table backing app/analysis/models/conversation_analysis.py.

This table is the durable store for ConversationAnalysisService (both the
live voice path in app/api/websocket_handler.py and the async/API-triggered
app/analysis/workers/analysis_worker.py) -- it existed as a SQLAlchemy model
since app/analysis was added but was never given a migration, so every write
to it failed with UndefinedTable until now.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_conversation_analyses"
down_revision = "20260720_slas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "conversation_analyses" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "conversation_analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("transcript", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sentiment", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("emotion", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fusion", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("lead_score", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("claims", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("verification", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("speakers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_conversation_analyses_conversation_id", "conversation_analyses", ["conversation_id"])
    op.create_index("ix_conversation_analyses_tenant_id", "conversation_analyses", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("conversation_analyses")
