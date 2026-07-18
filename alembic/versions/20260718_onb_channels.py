"""Add onboarding_contact_channels table (multi-select, one row per channel)."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_onb_channels"
down_revision = "20260718_onboarding_org_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "onboarding_contact_channels" in inspector.get_table_names():
        return
    op.create_table(
        "onboarding_contact_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "channel", name="uq_onboarding_contact_channel_tenant_channel"),
    )
    op.create_index("ix_onboarding_contact_channels_tenant_id", "onboarding_contact_channels", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("onboarding_contact_channels")
