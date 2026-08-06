"""Durable, tenant-scoped lead-nurturing flow models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id


class FlowDefinition(Base):
    __tablename__ = "flow_definitions"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, default="pre_sales")
    status = Column(String, nullable=False, default="draft", index=True)
    is_default = Column(Boolean, nullable=False, default=True)
    active_version_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    versions = relationship("FlowVersion", back_populates="flow", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("tenant_id", "category", "is_default", name="uq_flow_default_category"),)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Flow")


class FlowVersion(Base):
    __tablename__ = "flow_versions"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_id = Column(Uuid(as_uuid=True), ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="draft")
    graph = Column(JSONB, nullable=False, default=dict)
    settings = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)
    flow = relationship("FlowDefinition", back_populates="versions")
    __table_args__ = (UniqueConstraint("flow_id", "version", name="uq_flow_version"),)


class WorkflowTemplate(Base):
    """Follei-owned, immutable workflow template for an industry pack."""
    __tablename__ = "workflow_templates"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, nullable=False, index=True)
    slug = Column(String, nullable=False)
    industry = Column(String, nullable=False, default="universal")
    name = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="published")
    graph = Column(JSONB, nullable=False, default=dict)
    node_contracts = Column(JSONB, nullable=False, default=dict)
    settings = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("industry", "slug", "version", name="uq_workflow_template_version"),)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("WorkflowTemplate")


class TenantWorkflowInstance(Base):
    """Tenant-owned materialization of a template; customizations never mutate it."""
    __tablename__ = "tenant_workflow_instances"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(Uuid(as_uuid=True), ForeignKey("workflow_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    flow_id = Column(Uuid(as_uuid=True), ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False, unique=True)
    parent_instance_id = Column(Uuid(as_uuid=True), ForeignKey("tenant_workflow_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_node_key = Column(String, nullable=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    overrides = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    template = relationship("WorkflowTemplate")
    flow = relationship("FlowDefinition")
    parent_instance = relationship("TenantWorkflowInstance", remote_side=[id])

    __table_args__ = (UniqueConstraint("tenant_id", "template_id", "parent_instance_id", "parent_node_key", name="uq_tenant_template_parent_node"),)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("WorkflowInstance")


class FlowEnrollment(Base):
    __tablename__ = "flow_enrollments"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_id = Column(Uuid(as_uuid=True), ForeignKey("flow_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_version_id = Column(Uuid(as_uuid=True), ForeignKey("flow_versions.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="running", index=True)
    current_node_key = Column(String, nullable=False)
    current_node_id = Column(String, nullable=True, index=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    stop_reason = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    context = Column(JSONB, nullable=False, default=dict)
    enrollment_source = Column(String, nullable=False, default="automatic")
    eligibility_snapshot = Column(JSONB, nullable=False, default=dict)
    parent_enrollment_id = Column(Uuid(as_uuid=True), ForeignKey("flow_enrollments.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_node_key = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("lead_id", "flow_version_id", name="uq_flow_enrollment_lead_version"),)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Enrollment")


class FlowExecutionStep(Base):
    __tablename__ = "flow_execution_steps"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(Uuid(as_uuid=True), ForeignKey("flow_enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = Column(String, nullable=False)
    node_id = Column(String, nullable=True, index=True)
    action_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")
    attempt = Column(Integer, nullable=False, default=1)
    idempotency_key = Column(String, nullable=False, unique=True)
    output = Column(JSONB, nullable=False, default=dict)
    decision = Column(JSONB, nullable=False, default=dict)
    verification = Column(JSONB, nullable=False, default=dict)
    audit_metadata = Column(JSONB, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("FlowStep")


class WorkflowApproval(Base):
    """Canonical human/system approval record for consequential workflow actions."""
    __tablename__ = "workflow_approvals"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_instance_id = Column(Uuid(as_uuid=True), ForeignKey("tenant_workflow_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    enrollment_id = Column(Uuid(as_uuid=True), ForeignKey("flow_enrollments.id", ondelete="CASCADE"), nullable=True, index=True)
    node_key = Column(String, nullable=False)
    node_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sla_due_at = Column(DateTime, nullable=True)
    notification_status = Column(String, nullable=False, default="queued")
    requested_payload = Column(JSONB, nullable=False, default=dict)
    decision_metadata = Column(JSONB, nullable=False, default=dict)
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("WorkflowApproval")


class CommunicationAsset(Base):
    __tablename__ = "communication_assets"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    object_key = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    category = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ready")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
