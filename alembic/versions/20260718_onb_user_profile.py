"""Add onboarding user-profile fields to users: mobile_number, job_title, onboarding_terms_accepted_at."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_onb_user_profile"
down_revision = "20260718_onb_goals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "mobile_number" not in columns:
        op.add_column("users", sa.Column("mobile_number", sa.String(length=32), nullable=True))
    if "job_title" not in columns:
        op.add_column("users", sa.Column("job_title", sa.String(length=120), nullable=True))
    if "onboarding_terms_accepted_at" not in columns:
        op.add_column("users", sa.Column("onboarding_terms_accepted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding_terms_accepted_at")
    op.drop_column("users", "job_title")
    op.drop_column("users", "mobile_number")
