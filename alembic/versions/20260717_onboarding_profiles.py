"""Add onboarding_profiles table, one row per tenant."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_onboarding_profiles"
down_revision = "20260717_knowledge_sync_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "onboarding_profiles" in inspector.get_table_names():
        return
    op.create_table(
        "onboarding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("country_region", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_onboarding_profiles_tenant_id"),
    )
    op.create_index("ix_onboarding_profiles_tenant_id", "onboarding_profiles", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.drop_table("onboarding_profiles")
