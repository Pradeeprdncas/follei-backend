"""Durable tenant-scoped flexible memory documents."""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from app.database.base import Base


class KnowledgeMemory(Base):
    __tablename__ = "knowledge_memories"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    subject_type = Column(String(40), nullable=False, default="tenant")
    subject_id = Column(String(120), nullable=False)
    memory_layer = Column(String(20), nullable=False, default="mid_term")
    memory_type = Column(String(60), nullable=False)
    content = Column(JSON, nullable=False, default=dict)
    searchable_text = Column(Text, nullable=True)
    source_type = Column(String(40), nullable=True)
    source_id = Column(String(120), nullable=True)
    confidence = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index("ix_knowledge_memories_tenant_subject", "tenant_id", "subject_type", "subject_id"),
        Index("ix_knowledge_memories_tenant_type", "tenant_id", "memory_type"),
    )
