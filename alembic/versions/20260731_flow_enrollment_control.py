"""Add flow enrollment control identifiers and trigger settings.

Revision ID: 20260731_flow_enrollment_control
Revises: 20260730_flow_builder
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260731_flow_enrollment_control"
down_revision = "20260730_flow_builder"
branch_labels = None
depends_on = None


def _node_id(version_id: str, key: str) -> str:
    return "NODE_" + uuid.uuid5(uuid.UUID(str(version_id)), str(key)).hex[:16].upper()


def upgrade() -> None:
    op.add_column("flow_enrollments", sa.Column("public_id", sa.String(), nullable=True))
    op.add_column("flow_enrollments", sa.Column("current_node_id", sa.String(), nullable=True))
    op.add_column("flow_enrollments", sa.Column("enrollment_source", sa.String(), nullable=True))
    op.add_column("flow_enrollments", sa.Column("eligibility_snapshot", postgresql.JSONB(), nullable=True))
    op.add_column("flow_execution_steps", sa.Column("public_id", sa.String(), nullable=True))
    op.add_column("flow_execution_steps", sa.Column("node_id", sa.String(), nullable=True))

    bind = op.get_bind()
    versions = bind.execute(sa.text("SELECT id, graph, settings FROM flow_versions")).mappings().all()
    graph_by_version: dict[str, dict] = {}
    for row in versions:
        graph = dict(row["graph"] or {})
        nodes = list(graph.get("nodes") or [])
        for node in nodes:
            node.setdefault("id", _node_id(str(row["id"]), str(node.get("key") or "node")))
        graph["nodes"] = nodes
        settings = {
            "auto_enroll_new_leads": True,
            "auto_enroll_existing": False,
            "start_immediately": True,
            **dict(row["settings"] or {}),
        }
        bind.execute(
            sa.text("UPDATE flow_versions SET graph = CAST(:graph AS jsonb), settings = CAST(:settings AS jsonb) WHERE id = :id"),
            {"id": row["id"], "graph": __import__("json").dumps(graph), "settings": __import__("json").dumps(settings)},
        )
        graph_by_version[str(row["id"])] = {str(node.get("key")): str(node.get("id")) for node in nodes}

    enrollments = bind.execute(sa.text("SELECT id, flow_version_id, current_node_key FROM flow_enrollments")).mappings().all()
    for row in enrollments:
        current_node_id = graph_by_version.get(str(row["flow_version_id"]), {}).get(str(row["current_node_key"]))
        bind.execute(
            sa.text(
                "UPDATE flow_enrollments SET public_id=:public_id, current_node_id=:node_id, "
                "enrollment_source='migration_backfill', eligibility_snapshot=CAST('{}' AS jsonb) WHERE id=:id"
            ),
            {"id": row["id"], "public_id": "ENROLLME_" + str(row["id"]).replace("-", "")[:12].upper(), "node_id": current_node_id},
        )

    steps = bind.execute(sa.text("SELECT id, enrollment_id, node_key FROM flow_execution_steps")).mappings().all()
    enrollment_versions = {
        str(row["id"]): str(row["flow_version_id"])
        for row in bind.execute(sa.text("SELECT id, flow_version_id FROM flow_enrollments")).mappings()
    }
    for row in steps:
        version_id = enrollment_versions.get(str(row["enrollment_id"]))
        node_id = graph_by_version.get(version_id or "", {}).get(str(row["node_key"]))
        bind.execute(
            sa.text("UPDATE flow_execution_steps SET public_id=:public_id, node_id=:node_id WHERE id=:id"),
            {"id": row["id"], "public_id": "FLOWSTEP_" + str(row["id"]).replace("-", "")[:12].upper(), "node_id": node_id},
        )

    op.alter_column("flow_enrollments", "public_id", nullable=False)
    op.alter_column("flow_enrollments", "enrollment_source", nullable=False)
    op.alter_column("flow_enrollments", "eligibility_snapshot", nullable=False)
    op.alter_column("flow_execution_steps", "public_id", nullable=False)
    op.create_index("ix_flow_enrollments_public_id", "flow_enrollments", ["public_id"], unique=True)
    op.create_index("ix_flow_enrollments_current_node_id", "flow_enrollments", ["current_node_id"])
    op.create_index("ix_flow_execution_steps_public_id", "flow_execution_steps", ["public_id"], unique=True)
    op.create_index("ix_flow_execution_steps_node_id", "flow_execution_steps", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_flow_execution_steps_node_id", table_name="flow_execution_steps")
    op.drop_index("ix_flow_execution_steps_public_id", table_name="flow_execution_steps")
    op.drop_index("ix_flow_enrollments_current_node_id", table_name="flow_enrollments")
    op.drop_index("ix_flow_enrollments_public_id", table_name="flow_enrollments")
    op.drop_column("flow_execution_steps", "node_id")
    op.drop_column("flow_execution_steps", "public_id")
    op.drop_column("flow_enrollments", "eligibility_snapshot")
    op.drop_column("flow_enrollments", "enrollment_source")
    op.drop_column("flow_enrollments", "current_node_id")
    op.drop_column("flow_enrollments", "public_id")
