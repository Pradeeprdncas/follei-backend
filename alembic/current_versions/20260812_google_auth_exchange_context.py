"""Store safe Google login handoff context.

Revision ID: 20260812_google_context
Revises: 20260811_google_auth
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_google_context"
down_revision = "20260811_google_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "oauth_login_exchanges",
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_login_exchanges", "context")
