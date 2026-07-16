"""ConversationAnalysis model — separate 1:1 table for analysis results.

Kept separate from Conversation to allow independent read/write granularity,
different lifecycle (analysis may complete after conversation ends), and
clean schema evolution without touching the core conversation model.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref

from app.database.base import Base


class ConversationAnalysis(Base):
    __tablename__ = "conversation_analyses"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tenant_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="pending")

    # Structured outputs (JSONB — queryable, indexable, schema-flexible)
    transcript = Column(JSONB, nullable=False, default=dict)
    sentiment = Column(JSONB, nullable=False, default=dict)
    emotion = Column(JSONB, nullable=False, default=dict)
    fusion = Column(JSONB, nullable=False, default=dict)
    lead_score = Column(JSONB, nullable=False, default=dict)
    claims = Column(JSONB, nullable=False, default=list)
    verification = Column(JSONB, nullable=False, default=list)
    summary = Column(Text, nullable=True)
    speakers = Column(JSONB, nullable=False, default=list)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", backref=backref("analysis", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "tenant_id": str(self.tenant_id),
            "status": self.status,
            "transcript": self.transcript,
            "sentiment": self.sentiment,
            "emotion": self.emotion,
            "fusion": self.fusion,
            "lead_score": self.lead_score,
            "claims": self.claims,
            "verification": self.verification,
            "summary": self.summary,
            "speakers": self.speakers,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
