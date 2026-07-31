"""Tenant-owned email provider connections with encrypted credentials."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid

from app.database.base import Base


class TenantEmailConnection(Base):
    __tablename__ = "tenant_email_connections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(24), nullable=False, index=True)  # gmail | brevo
    email_address = Column(String(320), nullable=False, index=True)
    sender_name = Column(String(160), nullable=True)

    encrypted_api_key = Column(Text, nullable=True)
    encrypted_app_password = Column(Text, nullable=True)
    auth_type = Column(String(32), nullable=False, default="app_password")
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    oauth_scopes = Column(JSON, nullable=True)
    provider_account_id = Column(String(255), nullable=True)
    gmail_history_id = Column(String(64), nullable=True)
    token_updated_at = Column(DateTime, nullable=True)

    imap_host = Column(String(255), nullable=True)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    imap_last_uid = Column(BigInteger, nullable=True)

    enabled = Column(Boolean, nullable=False, default=True)
    verified = Column(Boolean, nullable=False, default=False)
    auto_reply_enabled = Column(Boolean, nullable=False, default=True)
    allow_inbound_lead_creation = Column(Boolean, nullable=False, default=True)
    campaign_enabled = Column(Boolean, nullable=False, default=True)

    status = Column(String(32), nullable=False, default="configured", index=True)
    last_polled_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "email_address",
            name="uq_tenant_email_connection_provider_address",
        ),
    )


class EmailOAuthState(Base):
    """Single-use tenant-bound OAuth transaction and server-only PKCE verifier."""

    __tablename__ = "email_oauth_states"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(24), nullable=False, default="gmail")
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    encrypted_code_verifier = Column(Text, nullable=False)
    expected_email = Column(String(320), nullable=True)
    sender_name = Column(String(160), nullable=True)
    auto_reply_enabled = Column(Boolean, nullable=False, default=True)
    allow_inbound_lead_creation = Column(Boolean, nullable=False, default=True)
    campaign_enabled = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
