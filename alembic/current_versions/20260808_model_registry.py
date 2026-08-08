"""Reconcile models that were mounted before canonical ORM registration.

Revision ID: 20260808_model_registry
Revises: 20260808_tenant_contact_policy
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260808_model_registry"
down_revision = "20260808_tenant_contact_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "conversation_analyses" not in inspector.get_table_names():
        op.create_table(
            "conversation_analyses",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_conversation_analyses_conversation_id", "conversation_analyses", ["conversation_id"], unique=True)
        op.create_index("ix_conversation_analyses_id", "conversation_analyses", ["id"])
        op.create_index("ix_conversation_analyses_tenant_id", "conversation_analyses", ["tenant_id"])


def downgrade() -> None:
    # The squashed baseline owns this table. This revision only reconciles
    # installations that reached the old head without it.
    pass
