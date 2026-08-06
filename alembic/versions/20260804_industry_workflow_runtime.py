"""Add versioned workflow templates, tenant instances, approvals and node evidence.

Revision ID: 20260804_industry_workflow_runtime
Revises: 20260731_flow_enrollment_control
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260804_industry_workflow_runtime"
down_revision = "20260731_flow_enrollment_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic creates this column as VARCHAR(32), but this revision ID is 34
    # characters. Widen it inside the same transaction before Alembic records
    # the new revision, otherwise upgrades from 20260731 fail after the DDL.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("public_id", sa.String(), nullable=False, unique=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("industry", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("graph", postgresql.JSONB(), nullable=False),
        sa.Column("node_contracts", postgresql.JSONB(), nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint("industry", "slug", "version", name="uq_workflow_template_version"),
    )
    op.create_index("ix_workflow_templates_public_id", "workflow_templates", ["public_id"], unique=True)
    op.create_table(
        "tenant_workflow_instances",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("public_id", sa.String(), nullable=False, unique=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("workflow_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("flow_id", sa.Uuid(), sa.ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("parent_instance_id", sa.Uuid(), sa.ForeignKey("tenant_workflow_instances.id", ondelete="CASCADE")),
        sa.Column("parent_node_key", sa.String()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("overrides", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "template_id", "parent_instance_id", "parent_node_key", name="uq_tenant_template_parent_node"),
    )
    for name, columns in (("ix_tenant_workflow_instances_public_id", ["public_id"]), ("ix_tenant_workflow_instances_tenant_id", ["tenant_id"]), ("ix_tenant_workflow_instances_template_id", ["template_id"]), ("ix_tenant_workflow_instances_parent_instance_id", ["parent_instance_id"]), ("ix_tenant_workflow_instances_status", ["status"])):
        op.create_index(name, "tenant_workflow_instances", columns, unique=name.endswith("public_id"))
    op.add_column("flow_enrollments", sa.Column("parent_enrollment_id", sa.Uuid(), sa.ForeignKey("flow_enrollments.id", ondelete="CASCADE")))
    op.add_column("flow_enrollments", sa.Column("parent_node_key", sa.String()))
    op.create_index("ix_flow_enrollments_parent_enrollment_id", "flow_enrollments", ["parent_enrollment_id"])
    for column in ("decision", "verification", "audit_metadata"):
        op.add_column("flow_execution_steps", sa.Column(column, postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_table(
        "workflow_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("public_id", sa.String(), nullable=False, unique=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_instance_id", sa.Uuid(), sa.ForeignKey("tenant_workflow_instances.id", ondelete="CASCADE")),
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("flow_enrollments.id", ondelete="CASCADE")),
        sa.Column("node_key", sa.String(), nullable=False), sa.Column("node_id", sa.String()),
        sa.Column("action", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.id", ondelete="SET NULL")),
        sa.Column("assigned_to", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("sla_due_at", sa.DateTime()), sa.Column("notification_status", sa.String(), nullable=False),
        sa.Column("requested_payload", postgresql.JSONB(), nullable=False), sa.Column("decision_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False), sa.Column("decided_at", sa.DateTime()),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    for name, columns in (("ix_workflow_approvals_public_id", ["public_id"]), ("ix_workflow_approvals_tenant_id", ["tenant_id"]), ("ix_workflow_approvals_workflow_instance_id", ["workflow_instance_id"]), ("ix_workflow_approvals_enrollment_id", ["enrollment_id"]), ("ix_workflow_approvals_status", ["status"])):
        op.create_index(name, "workflow_approvals", columns, unique=name.endswith("public_id"))


def downgrade() -> None:
    op.drop_table("workflow_approvals")
    op.drop_column("flow_execution_steps", "audit_metadata")
    op.drop_column("flow_execution_steps", "verification")
    op.drop_column("flow_execution_steps", "decision")
    op.drop_index("ix_flow_enrollments_parent_enrollment_id", table_name="flow_enrollments")
    op.drop_column("flow_enrollments", "parent_node_key")
    op.drop_column("flow_enrollments", "parent_enrollment_id")
    op.drop_table("tenant_workflow_instances")
    op.drop_table("workflow_templates")
