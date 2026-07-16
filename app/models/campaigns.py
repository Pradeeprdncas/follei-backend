"""Campaign Models - Email, WhatsApp, SMS, Multi-channel campaigns."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Text, Enum as SQLEnum, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base
from app.core.public_id import generate_public_id


class CampaignType(str, enum.Enum):
    """Campaign channel types."""
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VOICE = "voice"
    MULTI_CHANNEL = "multi_channel"


class CampaignStatus(str, enum.Enum):
    """Campaign lifecycle states."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class DeliveryStatus(str, enum.Enum):
    """Message delivery status."""
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    REPLIED = "replied"
    UNSUBSCRIBED = "unsubscribed"


class Campaign(Base):
    """Campaign entity for multi-channel marketing."""
    __tablename__ = "campaigns"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(SQLEnum(CampaignType), nullable=False)
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False)

    # Message content
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)

    # Scheduling
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    schedule_config = Column(JSONB, nullable=True)

    # Targeting
    target_audience = Column(JSONB, nullable=True)

    # Tracking settings
    tracking_config = Column(JSONB, nullable=True)

    # Analytics snapshot (non-normalised stats)
    analytics = Column(JSONB, nullable=True)

    # Stats
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    bounced_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    bounce_rate = Column(Integer, default=0)
    unsubscribe_count = Column(Integer, default=0)
    complaint_count = Column(Integer, default=0)

    # Idempotency / execution lock
    processing_started_at = Column(DateTime, nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Campaign")

    tenant = relationship("Tenant", back_populates="campaigns")
    messages = relationship("CampaignMessage", back_populates="campaign", cascade="all, delete-orphan")
    metrics = relationship("CampaignMetric", back_populates="campaign", cascade="all, delete-orphan")
    inbound_emails = relationship("InboundEmail", back_populates="campaign", cascade="all, delete-orphan")


class CampaignMessage(Base):
    """Individual message sent as part of a campaign."""
    __tablename__ = "campaign_messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    campaign_id = Column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    channel = Column(SQLEnum(CampaignType), nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)

    status = Column(SQLEnum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)

    provider_message_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    extra_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="messages")
    lead = relationship("Lead", back_populates="campaign_messages")


class CampaignMetric(Base):
    """Per-campaign metric event (open, click, reply, etc.)."""
    __tablename__ = "campaign_metrics"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    campaign_id = Column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_type = Column(String, nullable=False, index=True)
    value = Column(Integer, default=0)
    metadata_ = Column("metadata", JSONB, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="metrics")


class InboundEmail(Base):
    """Inbound email received via webhook."""
    __tablename__ = "inbound_emails"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    from_email = Column(String, nullable=True)
    to_email = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    provider = Column(String, default="brevo")
    event_type = Column(String, default="inbound")
    raw_payload = Column(JSONB, default=dict)
    received_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="inbound_emails")


class OutboxMessage(Base):
    """Outbox pattern — messages queued for async delivery."""
    __tablename__ = "outbox_messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_message_id = Column(Uuid(as_uuid=True), ForeignKey("campaign_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True, index=True)

    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    html_body = Column(Text, nullable=True)
    sender_name = Column(String, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)

    status = Column(String, default="pending", nullable=False, index=True)
    priority = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    provider = Column(String, nullable=True)
    provider_message_id = Column(String, nullable=True)
    provider_response = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")


class ProviderLog(Base):
    """Observability log for every provider call."""
    __tablename__ = "provider_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    outbox_id = Column(Uuid(as_uuid=True), ForeignKey("outbox_messages.id", ondelete="SET NULL"), nullable=True, index=True)

    provider = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=True)
    status = Column(String, nullable=False)
    success = Column(Boolean, default=False)
    latency_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    cost = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    request_id = Column(String, nullable=True)
    raw_response = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant")
    campaign = relationship("Campaign")


# Backward-compatible aliases — these models moved to their proper modules.
# Direct imports from app.models.campaigns still work during migration.
from app.models.knowledge.knowledge_base import KnowledgeBase  # noqa: F401, E402
from app.models.leads.lead_score import LeadScore  # noqa: F401, E402
from app.models.conversations.conversation import Conversation  # noqa: F401, E402
from app.models.conversations.conversation import Message  # noqa: F401, E402