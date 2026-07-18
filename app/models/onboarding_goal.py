"""Tenant's selected onboarding goals — a list (max 3, enforced server-side), own table."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid, UniqueConstraint

from app.database.base import Base


class OnboardingGoal(Base):
    __tablename__ = "onboarding_goals"
    __table_args__ = (UniqueConstraint("tenant_id", "goal", name="uq_onboarding_goal_tenant_goal"),)

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    goal = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
