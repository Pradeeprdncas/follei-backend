"""Add onboarding_goals table (multi-select, max 3 enforced at the API layer)."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_onb_goals"
down_revision = "20260718_onb_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "onboarding_goals" in inspector.get_table_names():
        return
    op.create_table(
        "onboarding_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("goal", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "goal", name="uq_onboarding_goal_tenant_goal"),
    )
    op.create_index("ix_onboarding_goals_tenant_id", "onboarding_goals", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("onboarding_goals")
