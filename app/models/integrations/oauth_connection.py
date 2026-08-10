"""Tenant-bound OAuth transactions and Google Workspace connections."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class IntegrationOAuthState(Base):
    __tablename__ = "integration_oauth_states"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Public identity sign-in starts before Follei has a tenant or user. The
    # authenticated connector flows still populate both fields.
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    provider = Column(String(32), nullable=False, index=True)
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    encrypted_code_verifier = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OAuthLoginExchange(Base):
    """Short-lived, one-use bridge from an OAuth popup to Follei JWTs."""

    __tablename__ = "oauth_login_exchanges"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class GoogleWorkspaceConnection(Base):
    __tablename__ = "google_workspace_connections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Uuid(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True)
    email_address = Column(String(320), nullable=False)
    provider_account_id = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="active", index=True)
    encrypted_access_token = Column(Text, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    scopes = Column(JSONB, nullable=False, default=list)
    enabled_resources = Column(JSONB, nullable=False, default=list)
    sync_cursors = Column(JSONB, nullable=False, default=dict)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_account_id", name="uq_google_workspace_tenant_account"),
    )
