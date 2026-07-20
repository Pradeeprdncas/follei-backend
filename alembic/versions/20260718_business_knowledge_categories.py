"""Add tenant-scoped approved business plans and customer segments."""
from alembic import op
import sqlalchemy as sa

revision = "20260718_biz_categories"
down_revision = "20260718_onb_complete"
branch_labels = None
depends_on = None


def _create_table(name: str, fields: list[sa.Column]) -> None:
    inspector = sa.inspect(op.get_bind())
    if name not in inspector.get_table_names():
        op.create_table(name, *fields)
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])


def upgrade() -> None:
    common = [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]
    _create_table("business_plans", [*common[:4], sa.Column("pricing", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *common[4:]])
    _create_table("customer_segments", [*common[:4], sa.Column("criteria", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *common[4:]])


def downgrade() -> None:
    op.drop_table("customer_segments")
    op.drop_table("business_plans")
