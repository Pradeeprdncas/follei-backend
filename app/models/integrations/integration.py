import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Uuid
from sqlalchemy.orm import relationship

from app.database.base import Base

class Integration(Base):
    """
    Global registry of available MCP tools/integrations (HubSpot, Salesforce, Gmail).
    Does NOT have a tenant_id, because this is globally defined by your platform.
    """
    __tablename__ = "integrations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    connections = relationship("IntegrationConnection", back_populates="integration")

class IntegrationConnection(Base):
    """
    A specific tenant's authorized connection to a tool (holds OAuth/API Keys).
    """
    __tablename__ = "integration_connections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id = Column(Uuid(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False)
    
    status = Column(String, default="active") # 'active', 'error', 'disconnected'
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="integration_connections")
    integration = relationship("Integration", back_populates="connections")
