"""Add industry/company_size fields to onboarding_profiles."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_onboarding_org_fields"
down_revision = "20260717_onboarding_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("onboarding_profiles")}
    if "industry" not in columns:
        op.add_column("onboarding_profiles", sa.Column("industry", sa.String(length=64), nullable=True))
    if "industry_other" not in columns:
        op.add_column("onboarding_profiles", sa.Column("industry_other", sa.String(length=255), nullable=True))
    if "company_size" not in columns:
        op.add_column("onboarding_profiles", sa.Column("company_size", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("onboarding_profiles", "company_size")
    op.drop_column("onboarding_profiles", "industry_other")
    op.drop_column("onboarding_profiles", "industry")
