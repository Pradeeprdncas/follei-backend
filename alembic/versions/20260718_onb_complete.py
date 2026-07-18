"""Add completed_at to onboarding_profiles."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_onb_complete"
down_revision = "20260718_onb_user_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("onboarding_profiles")}
    if "completed_at" not in columns:
        op.add_column("onboarding_profiles", sa.Column("completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("onboarding_profiles", "completed_at")
