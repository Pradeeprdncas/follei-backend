"""Durable cross-store synchronization events for the knowledge layer."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid

from app.database.base import Base


class KnowledgeSyncEvent(Base):
    """One tenant-scoped business event with independently retryable deliveries."""

    __tablename__ = "knowledge_sync_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(96), nullable=False, index=True)
    aggregate_type = Column(String(64), nullable=False)
    aggregate_id = Column(Uuid(as_uuid=True), nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    deliveries = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_knowledge_sync_events_tenant_idempotency", "tenant_id", "idempotency_key", unique=True),
        Index("ix_knowledge_sync_events_status_created", "status", "created_at"),
    )