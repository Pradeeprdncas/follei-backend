"""Tenant-owned SMS, WhatsApp, and voice provider connections."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, Uuid

from app.database.base import Base


class TenantChannelConnection(Base):
    __tablename__ = "tenant_channel_connections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(24), nullable=False, index=True)  # sms | whatsapp | voice
    provider = Column(String(32), nullable=False, index=True)  # twilio | meta | brevo
    identity = Column(String(255), nullable=False)
    provider_account_id = Column(String(255), nullable=True)
    encrypted_account_sid = Column(Text, nullable=True)
    encrypted_auth_token = Column(Text, nullable=True)
    encrypted_api_key = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    verified = Column(Boolean, nullable=False, default=False)
    inbound_enabled = Column(Boolean, nullable=False, default=True)
    campaign_enabled = Column(Boolean, nullable=False, default=False)
    status = Column(String(32), nullable=False, default="pending_verification", index=True)
    verification_metadata = Column(JSON, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", "provider", "identity", name="uq_tenant_channel_provider_identity"),
    )


class ChannelComplianceAcknowledgement(Base):
    __tablename__ = "channel_compliance_acknowledgements"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(Uuid(as_uuid=True), ForeignKey("tenant_channel_connections.id", ondelete="CASCADE"), nullable=False, unique=True)
    channel = Column(String(24), nullable=False)
    policy_version = Column(String(32), nullable=False)
    opt_in_acknowledged = Column(Boolean, nullable=False, default=False)
    stop_help_acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
