"""Canonical PostgreSQL control plane for all knowledge ingestion sources."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Uuid(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    page_count = Column(Integer, nullable=False, default=0)
    document_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_ingestion_runs_tenant_created", "tenant_id", "created_at"),)


class SourceIngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(48), nullable=False, index=True)
    target = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    attempt = Column(Integer, nullable=False, default=0)
    payload = Column(JSONB, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_ingestion_jobs_run_type", "run_id", "job_type"),)


class CategorySummary(Base):
    __tablename__ = "category_summaries"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    category_key = Column(String(64), nullable=False)
    category_group = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="missing")
    item_count = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    needs_review = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "category_key", name="uq_category_summary_tenant_key"),
        Index("ix_category_summaries_tenant_status", "tenant_id", "status"),
    )


class OnboardingConfirmation(Base):
    __tablename__ = "onboarding_confirmations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_key = Column(String(64), nullable=False)
    resolution = Column(String(32), nullable=False)
    note = Column(Text, nullable=True)
    confirmed_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "requirement_key", name="uq_confirmation_tenant_requirement"),
    )
