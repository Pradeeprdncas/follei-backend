"""Interaction model — logical grouping of messages within a conversation.

A conversation can have multiple interactions:
- A phone call (stored as compressed transcript in CallSession)
- A WhatsApp session (multiple individual messages)
- An email thread (multiple emails)
- A live chat session (multiple messages)
- An SMS exchange (multiple messages)
"""
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)

    interaction_type = Column(String, nullable=False)  # call, whatsapp, email, chat, sms
    channel = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)

    # Timing
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Denormalized analysis fields
    sentiment = Column(JSON, nullable=True)
    emotion = Column(JSON, nullable=True)
    summary = Column(Text, nullable=True)
    analysis_status = Column(String, default="pending", nullable=False)
    analysis_details = Column(JSON, nullable=True)

    # Lead score snapshot at interaction level
    lead_temperature = Column(String, nullable=True)
    lead_score = Column(Float, nullable=True)

    metadata_ = Column("metadata", JSON, default=dict, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="interactions")
    messages = relationship("Message", back_populates="interaction", cascade="all, delete-orphan")
    call_session = relationship("CallSession", back_populates="interaction", uselist=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Interaction")
