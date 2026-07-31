"""Add durable lead nurturing flow engine.

Revision ID: 20260730_flow_builder
Revises: 20260730_tenant_gmail_oauth
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260730_flow_builder"
down_revision = "20260730_tenant_gmail_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("flow_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_id", sa.String(), nullable=False, unique=True), sa.Column("name", sa.String(), nullable=False), sa.Column("category", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("is_default", sa.Boolean(), nullable=False), sa.Column("active_version_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "category", "is_default", name="uq_flow_default_category"))
    op.create_index("ix_flow_definitions_tenant_id", "flow_definitions", ["tenant_id"])
    op.create_index("ix_flow_definitions_status", "flow_definitions", ["status"])
    op.create_table("flow_versions",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("graph", postgresql.JSONB(), nullable=False), sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("published_at", sa.DateTime()), sa.UniqueConstraint("flow_id", "version", name="uq_flow_version"))
    op.create_index("ix_flow_versions_tenant_id", "flow_versions", ["tenant_id"]); op.create_index("ix_flow_versions_flow_id", "flow_versions", ["flow_id"])
    op.create_table("flow_enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False), sa.Column("flow_version_id", sa.Uuid(), sa.ForeignKey("flow_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_node_key", sa.String(), nullable=False), sa.Column("next_run_at", sa.DateTime()), sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String()), sa.Column("last_error", sa.Text()), sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("lead_id", "flow_version_id", name="uq_flow_enrollment_lead_version"))
    for name, cols in (("ix_flow_enrollments_tenant_id", ["tenant_id"]), ("ix_flow_enrollments_lead_id", ["lead_id"]), ("ix_flow_enrollments_status", ["status"]), ("ix_flow_enrollments_next_run_at", ["next_run_at"])):
        op.create_index(name, "flow_enrollments", cols)
    op.create_table("flow_execution_steps",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("flow_enrollments.id", ondelete="CASCADE"), nullable=False), sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(), nullable=False), sa.Column("action_type", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("idempotency_key", sa.String(), nullable=False, unique=True), sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()))
    op.create_index("ix_flow_execution_steps_tenant_id", "flow_execution_steps", ["tenant_id"]); op.create_index("ix_flow_execution_steps_enrollment_id", "flow_execution_steps", ["enrollment_id"])
    op.create_table("communication_assets",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False), sa.Column("object_key", sa.String(), nullable=False, unique=True), sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(), nullable=False), sa.Column("category", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_communication_assets_tenant_id", "communication_assets", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("communication_assets"); op.drop_table("flow_execution_steps"); op.drop_table("flow_enrollments"); op.drop_table("flow_versions"); op.drop_table("flow_definitions")
