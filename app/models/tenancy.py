import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id

_DEFAULT_BUSINESS_HOURS = {
    "mon": ["09:00", "18:00"],
    "tue": ["09:00", "18:00"],
    "wed": ["09:00", "18:00"],
    "thu": ["09:00", "18:00"],
    "fri": ["09:00", "18:00"],
    "sat": ["10:00", "14:00"],
    "sun": None,
}

_DEFAULT_CHANNEL_CONFIG = {
    "email": {"enabled": False},
    "voice": {"enabled": False},
    "sms": {"enabled": False},
}


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True, nullable=False)
    domain = Column(String, unique=True, index=True, nullable=True)
    slug = Column(String, index=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    industry = Column(String, nullable=True)
    country_region = Column(String, nullable=True)
    website = Column(String, nullable=True)
    selected_channels = Column(JSONB, nullable=True)
    onboarding_profile = Column(JSONB, nullable=True)
    plan = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)
    trial_ends_at = Column(DateTime, nullable=True)

    # Multi-channel fields
    business_phone_number = Column(String, nullable=True)
    business_email = Column(String, nullable=True)
    timezone = Column(String, default="Asia/Kolkata", nullable=False)
    business_hours = Column(JSONB, nullable=True)
    forwarding_number = Column(String, nullable=True)
    auto_reply_enabled = Column(Boolean, default=False, nullable=False)
    channel_config = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Tenant")

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="tenant", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    integration_connections = relationship(
        "IntegrationConnection",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    leads = relationship("Lead", back_populates="tenant", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="tenant", cascade="all, delete-orphan")
    knowledge_base = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    public_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    status = Column(String, default="active", nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    mobile_number = Column(String(32), nullable=True)
    # Onboarding wizard's "Role" field (e.g. "Sales Manager", "Founder") — distinct
    # from `role` above, which is the RBAC role ("admin") assigned at registration.
    job_title = Column(String(120), nullable=True)
    onboarding_terms_accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("User")

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    assigned_agent_tasks = relationship(
        "AgentTask",
        back_populates="assignee",
        foreign_keys="AgentTask.assigned_by",
    )
    created_agent_feedback = relationship(
        "AgentFeedback",
        back_populates="creator",
        foreign_keys="AgentFeedback.created_by",
    )
    created_agent_prompt_versions = relationship(
        "AgentPromptVersion",
        back_populates="creator",
        foreign_keys="AgentPromptVersion.created_by",
    )
    created_agent_versions = relationship(
        "AgentVersion",
        back_populates="creator",
        foreign_keys="AgentVersion.created_by",
    )

