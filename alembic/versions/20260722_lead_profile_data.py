"""Retain structured non-core lead import fields on the operational lead."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260722_lead_profile_data"
down_revision = "20260720_learning_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("leads")}
    if "profile_data" not in columns:
        op.add_column("leads", sa.Column("profile_data", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("leads")}
    if "profile_data" in columns:
        op.drop_column("leads", "profile_data")
