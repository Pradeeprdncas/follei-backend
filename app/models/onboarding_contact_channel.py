"""Tenant's selected onboarding contact channels — a list, so its own table."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid, UniqueConstraint

from app.database.base import Base


class OnboardingContactChannel(Base):
    __tablename__ = "onboarding_contact_channels"
    __table_args__ = (UniqueConstraint("tenant_id", "channel", name="uq_onboarding_contact_channel_tenant_channel"),)

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
