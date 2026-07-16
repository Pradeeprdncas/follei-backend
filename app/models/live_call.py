import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text, Float, Uuid
from sqlalchemy.orm import relationship
from app.database.base import Base


class LiveCallTranscription(Base):
    __tablename__ = "live_call_transcriptions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    user_phone = Column(String, nullable=True)
    agent_phone = Column(String, nullable=True)

    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    languages = Column(JSON, default=list, nullable=False)

    user_messages = Column(JSON, default=list, nullable=False)
    ai_messages = Column(JSON, default=list, nullable=False)

    conversation_data = Column(JSON, default=dict, nullable=False)

    confidence_score = Column(Float, nullable=True)

    status = Column(String, default="active", nullable=False)
    transcription_model = Column(String, default="whisper-huggingface", nullable=False)
    ai_model = Column(String, default="mistral-7b", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation")
    agent = relationship("Agent")


class CallTranscriptionChunk(Base):
    __tablename__ = "call_transcription_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    live_call_id = Column(Uuid(as_uuid=True), ForeignKey("live_call_transcriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    speaker = Column(String, nullable=False)
    text = Column(Text, nullable=False)

    start_timestamp = Column(Float, nullable=False)
    end_timestamp = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)
    language = Column(String, nullable=True)

    is_processed = Column(String, default="pending", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    live_call = relationship("LiveCallTranscription")
    tenant = relationship("Tenant")
