import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id

class Agent(Base):
    """
    Represents an autonomous AI worker within a tenant.
    """
    __tablename__ = "agents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    
    name = Column(String, nullable=False)
    role = Column(String, nullable=False) # e.g., 'SDR', 'Support'
    system_prompt = Column(String, nullable=False)
    tools = Column(ARRAY(String), default=list) # Assigned MCP tool names
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Agent")

    tenant = relationship("Tenant", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
    actions = relationship("AgentAction", back_populates="agent")
    analytics = relationship("AgentAnalytics", back_populates="agent")
    confidence_scores = relationship("AgentConfidenceScore", back_populates="agent")
    errors = relationship("AgentError", back_populates="agent")
    feedback = relationship("AgentFeedback", back_populates="agent")
    learning_events = relationship("AgentLearningEvent", back_populates="agent")
    memories = relationship("AgentMemory", back_populates="agent")
    plans = relationship("AgentPlan", back_populates="agent")
    prompt_versions = relationship("AgentPromptVersion", back_populates="agent")
    sessions = relationship("AgentSession", back_populates="agent")
    tasks = relationship("AgentTask", back_populates="agent")
    tool_calls = relationship("AgentToolCall", back_populates="agent")
    versions = relationship("AgentVersion", back_populates="agent")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, nullable=False, default="active")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="sessions")
    conversation = relationship("Conversation", back_populates="agent_sessions")
    actions = relationship("AgentAction", back_populates="session")


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    task_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String, default="queued", nullable=False)
    due_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="tasks")
    assignee = relationship("User", back_populates="assigned_agent_tasks", foreign_keys=[assigned_by])
    actions = relationship("AgentAction", back_populates="task")
    plans = relationship("AgentPlan", back_populates="task")


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(Uuid(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    result = Column(JSON, nullable=True)
    status = Column(String, default="completed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="actions")
    session = relationship("AgentSession", back_populates="actions")
    task = relationship("AgentTask", back_populates="actions")


class AgentAnalytics(Base):
    __tablename__ = "agent_analytics"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    metrics = Column(JSON, default=dict, nullable=False)
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="analytics")


class AgentConfidenceScore(Base):
    __tablename__ = "agent_confidence_scores"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    score = Column(Numeric, nullable=False)
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="confidence_scores")
    message = relationship("Message", back_populates="agent_confidence_scores")


class AgentError(Base):
    __tablename__ = "agent_errors"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    error_type = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    context = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="errors")


class AgentFeedback(Base):
    __tablename__ = "agent_feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="feedback")
    message = relationship("Message", back_populates="agent_feedback")
    creator = relationship("User", back_populates="created_agent_feedback", foreign_keys=[created_by])


class AgentLearningEvent(Base):
    __tablename__ = "agent_learning_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="learning_events")


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    memory_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    vector_id = Column(Uuid(as_uuid=True), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="memories")
    customer = relationship("Customer", back_populates="agent_memories")


class AgentPlan(Base):
    __tablename__ = "agent_plans"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True)
    plan = Column(JSON, default=dict, nullable=False)
    status = Column(String, default="draft", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="plans")
    task = relationship("AgentTask", back_populates="plans")


class AgentPromptVersion(Base):
    __tablename__ = "agent_prompt_versions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=False)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="prompt_versions")
    creator = relationship("User", back_populates="created_agent_prompt_versions", foreign_keys=[created_by])


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    tool_name = Column(String, nullable=False)
    request = Column(JSON, default=dict, nullable=False)
    response = Column(JSON, nullable=True)
    status = Column(String, default="queued", nullable=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="tool_calls")


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    model = Column(String, nullable=True)
    system_prompt = Column(Text, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="versions")
    creator = relationship("User", back_populates="created_agent_versions", foreign_keys=[created_by])
