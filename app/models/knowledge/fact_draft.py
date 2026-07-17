"""Tenant-scoped extracted business facts awaiting a human decision."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, Uuid

from app.database.base import Base


class BusinessFactDraft(Base):
    """An auditable extracted fact. It is not operational data until approved."""

    __tablename__ = "business_fact_drafts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    fact_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    citation = Column(JSON, nullable=False, default=dict)
    extraction_confidence = Column(Numeric(4, 3), nullable=True)
    approval_status = Column(String(24), nullable=False, default="draft", index=True)
    reviewer = Column(String(120), nullable=True)
    review_reason = Column(Text, nullable=True)
    published_record_type = Column(String(64), nullable=True)
    published_record_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_business_fact_drafts_tenant_status", "tenant_id", "approval_status"),
    )
