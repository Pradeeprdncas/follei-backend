"""Durable tenant-scoped document indexing job."""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from app.database.base import Base


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    disposition = Column(String(24), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    payload = Column(JSON, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_indexing_jobs_tenant_created", "tenant_id", "created_at"),)
