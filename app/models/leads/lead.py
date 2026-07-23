import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id

class LeadTemperature(str):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    LOST = "lost"
    QUALIFIED = "qualified"
    CUSTOMER = "customer"

class Lead(Base):
    """
    Represents a prospective customer and their BANT/MEDDIC revenue scores.
    """
    __tablename__ = "leads"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    
    email = Column(String, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    status = Column(String, default="new") # 'new', 'qualified', 'disqualified', 'converted'
    revenue_score = Column(Integer, default=0)
    phone = Column(Integer, default=0)
    # Structured import fields that do not belong in the narrow operational CRM
    # columns (website, LinkedIn, title, location, source provenance, etc.).
    profile_data = Column(JSONB, nullable=True)

    # Lead temperature
    current_temperature = Column(String, default="cold", nullable=False)
    current_score = Column(Float, default=0.0, nullable=False)
    last_analysis_at = Column(DateTime, nullable=True)
    analysis_confidence = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="leads")
    conversations = relationship("Conversation", back_populates="lead")
    customers = relationship("Customer", back_populates="lead")
    campaign_messages = relationship("CampaignMessage", back_populates="lead")
    scores = relationship("LeadScore", back_populates="lead", order_by="LeadScore.created_at.desc()")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Lead")
