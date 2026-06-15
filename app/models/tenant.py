"""Tenant model for multi-tenancy."""
from sqlalchemy import Column, String, DateTime, Boolean
from datetime import datetime
from app.database.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
