"""Tenant onboarding profile: one row per tenant, separate from the tenants table."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid

from app.database.base import Base


class OnboardingProfile(Base):
    """Company-level onboarding details collected during setup, not bolted onto tenants."""

    __tablename__ = "onboarding_profiles"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    company_name = Column(String(255), nullable=False)
    website = Column(String(500), nullable=True)
    timezone = Column(String(64), nullable=False)
    country_region = Column(String(120), nullable=True)
    industry = Column(String(64), nullable=True)
    industry_other = Column(String(255), nullable=True)
    company_size = Column(String(16), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
