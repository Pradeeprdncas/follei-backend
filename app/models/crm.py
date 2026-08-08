"""Canonical, tenant-scoped CRM integration records."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class TenantCRMConnection(Base):
    __tablename__ = "tenant_crm_connections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="hubspot")
    status = Column(String(24), nullable=False, default="active", index=True)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    auth_type = Column(String(24), nullable=False, default="oauth")
    external_account_id = Column(String(255), nullable=True)
    scopes = Column(JSONB, nullable=False, default=list)
    sync_cursor = Column(JSONB, nullable=False, default=dict)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_tenant_crm_provider"),)


class CRMRecord(Base):
    """Normalized CRM object. Raw provider payloads are projected to FerretDB."""
    __tablename__ = "crm_records"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(Uuid(as_uuid=True), ForeignKey("tenant_crm_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    object_type = Column(String(32), nullable=False, index=True)
    external_id = Column(String(255), nullable=False)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    canonical_data = Column(JSONB, nullable=False, default=dict)
    provider_updated_at = Column(DateTime, nullable=True)
    source_revision = Column(Integer, nullable=False, default=1)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "object_type", "external_id", name="uq_crm_record_external"),
        Index("ix_crm_records_tenant_object", "tenant_id", "object_type"),
    )


class CRMSyncRun(Base):
    __tablename__ = "crm_sync_runs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(Uuid(as_uuid=True), ForeignKey("tenant_crm_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False, default="running", index=True)
    requested_resources = Column(JSONB, nullable=False, default=list)
    object_counts = Column(JSONB, nullable=False, default=dict)
    event_ids = Column(JSONB, nullable=False, default=list)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
