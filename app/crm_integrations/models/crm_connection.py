from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.database.base import Base


class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), unique=True, index=True, nullable=False)
    account_id = Column(Integer, ForeignKey("crm_accounts.id"), nullable=True)
    workspace_name = Column(String(255), nullable=False)
    login_email = Column(String(255), nullable=False)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    sync_scope = Column(String(50), default="contacts", nullable=False)
    allow_collab = Column(Boolean, default=True, nullable=False)
    auto_sync = Column(Boolean, default=True, nullable=False)
    status = Column(String(50), default="connected", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("CRMAccount", back_populates="connections")
