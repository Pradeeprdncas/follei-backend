"""LearningSignal — the System 6 learning loop's durable record.

One row per (action -> customer response -> outcome) event, tagged with a
polarity so the platform can measure how its actions actually land and nudge
future scoring. This is the "Performance Measurement" step of the proposal's
loop (Action -> Customer Response -> Outcome -> Performance Measurement ->
Model Update); LearningSignalService reads these to compute a per-tenant
calibration nudge. Deliberately a lightweight signal ledger, not a full
retraining pipeline.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base


class LearningSignal(Base):
    __tablename__ = "learning_signals"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)

    # What happened, and how it landed.
    action_type = Column(String, nullable=False)   # meeting_booked, deal_closed_won, support_escalated, ...
    outcome = Column(String, nullable=True)         # human-readable outcome
    polarity = Column(String, nullable=False)       # positive | negative | neutral
    weight = Column(Float, nullable=False, default=1.0)
    signal_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    tenant = relationship("Tenant")
