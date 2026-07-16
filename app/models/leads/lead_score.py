"""LeadScore model for lead scoring history."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base


class LeadScore(Base):
    """Lead scoring history."""
    __tablename__ = "lead_scores"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    score = Column(Integer, nullable=False)
    previous_score = Column(Integer, nullable=True)
    score_delta = Column(Integer, nullable=True)

    event_type = Column(String, nullable=False)
    event_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="scores")
    tenant = relationship("Tenant")
