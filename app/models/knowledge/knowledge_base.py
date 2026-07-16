"""KnowledgeBase model for RAG."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base


class KnowledgeBase(Base):
    """Knowledge base document for RAG."""
    __tablename__ = "knowledge_base"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_type = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    url = Column(String, nullable=True)

    status = Column(String, default="pending")
    chunk_count = Column(Integer, default=0)

    metadata_ = Column("metadata", JSONB, nullable=True)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="knowledge_base")
