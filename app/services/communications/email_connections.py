"""Encrypted tenant email connection access.

Environment settings remain a local-development fallback. Production routing
prefers tenant-owned PostgreSQL connections.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.crm_integrations.utils.encryption import EncryptionService
from app.models.integrations.email_connection import TenantEmailConnection


@dataclass(frozen=True)
class GmailMailbox:
    connection_id: str | None
    tenant_id: str
    email_address: str
    app_password: str
    sender_name: str
    imap_host: str
    smtp_host: str
    smtp_port: int
    imap_last_uid: int | None
    auto_reply_enabled: bool
    allow_inbound_lead_creation: bool
    auth_type: str = "app_password"
    gmail_history_id: str | None = None


@dataclass(frozen=True)
class BrevoAccount:
    connection_id: str | None
    tenant_id: str | None
    api_key: str
    sender_email: str
    sender_name: str


def _cipher() -> EncryptionService:
    settings = get_settings()
    key = settings.EMAIL_CREDENTIAL_ENCRYPTION_KEY or settings.SECRET_KEY
    return EncryptionService(key)


def encrypt_secret(value: str | None) -> str | None:
    clean = (value or "").strip()
    return _cipher().encrypt(clean) if clean else None


def decrypt_secret(value: str | None) -> str:
    return _cipher().decrypt(value) if value else ""


def gmail_mailboxes(db: Session) -> list[GmailMailbox]:
    rows = (
        db.query(TenantEmailConnection)
        .filter(
            TenantEmailConnection.provider == "gmail",
            TenantEmailConnection.enabled.is_(True),
            TenantEmailConnection.status.in_(("configured", "active")),
        )
        .order_by(TenantEmailConnection.created_at.asc())
        .all()
    )
    mailboxes = [
        GmailMailbox(
            connection_id=str(row.id),
            tenant_id=str(row.tenant_id),
            email_address=row.email_address.strip().lower(),
            app_password=decrypt_secret(row.encrypted_app_password).replace(" ", ""),
            sender_name=row.sender_name or "Follei",
            imap_host=row.imap_host or "imap.gmail.com",
            smtp_host=row.smtp_host or "smtp.gmail.com",
            smtp_port=int(row.smtp_port or 465),
            imap_last_uid=int(row.imap_last_uid) if row.imap_last_uid is not None else None,
            auto_reply_enabled=bool(row.auto_reply_enabled),
            allow_inbound_lead_creation=bool(row.allow_inbound_lead_creation),
            auth_type=row.auth_type or "app_password",
            gmail_history_id=row.gmail_history_id,
        )
        for row in rows
        if row.encrypted_app_password or (row.auth_type == "oauth" and row.encrypted_refresh_token)
    ]
    if mailboxes:
        return mailboxes

    settings = get_settings()
    if settings.GMAIL_MONITORED_EMAIL and settings.GMAIL_APP_PASSWORD and settings.GMAIL_DEFAULT_TENANT_ID:
        return [
            GmailMailbox(
                connection_id=None,
                tenant_id=str(UUID(settings.GMAIL_DEFAULT_TENANT_ID)),
                email_address=settings.GMAIL_MONITORED_EMAIL.strip().lower(),
                app_password=settings.GMAIL_APP_PASSWORD.replace(" ", ""),
                sender_name=settings.BREVO_SENDER_NAME or "Follei",
                imap_host=settings.GMAIL_IMAP_HOST,
                smtp_host=settings.GMAIL_SMTP_HOST,
                smtp_port=settings.GMAIL_SMTP_PORT,
                imap_last_uid=None,
                auto_reply_enabled=settings.GMAIL_AUTO_REPLY_ENABLED,
                allow_inbound_lead_creation=True,
                auth_type="app_password",
                gmail_history_id=None,
            )
        ]
    return []


def brevo_account(db: Session, tenant_id: str | UUID | None) -> BrevoAccount | None:
    row = None
    if tenant_id:
        row = (
            db.query(TenantEmailConnection)
            .filter(
                TenantEmailConnection.tenant_id == UUID(str(tenant_id)),
                TenantEmailConnection.provider == "brevo",
                TenantEmailConnection.enabled.is_(True),
                TenantEmailConnection.campaign_enabled.is_(True),
                TenantEmailConnection.status.in_(("configured", "active")),
            )
            .order_by(TenantEmailConnection.updated_at.desc())
            .first()
        )
    if row and row.encrypted_api_key:
        return BrevoAccount(
            connection_id=str(row.id),
            tenant_id=str(row.tenant_id),
            api_key=decrypt_secret(row.encrypted_api_key),
            sender_email=row.email_address,
            sender_name=row.sender_name or "Follei",
        )

    settings = get_settings()
    if settings.BREVO_API_KEY and settings.BREVO_SENDER_EMAIL:
        return BrevoAccount(
            connection_id=None,
            tenant_id=str(tenant_id) if tenant_id else None,
            api_key=settings.BREVO_API_KEY,
            sender_email=settings.BREVO_SENDER_EMAIL,
            sender_name=settings.BREVO_SENDER_NAME or "Follei",
        )
    return None


def has_gmail_oauth_sender(db: Session, tenant_id: str | UUID | None) -> bool:
    if not tenant_id:
        return False
    return db.query(TenantEmailConnection.id).filter(
        TenantEmailConnection.tenant_id == UUID(str(tenant_id)),
        TenantEmailConnection.provider == "gmail",
        TenantEmailConnection.auth_type == "oauth",
        TenantEmailConnection.enabled.is_(True),
        TenantEmailConnection.verified.is_(True),
        TenantEmailConnection.campaign_enabled.is_(True),
        TenantEmailConnection.status == "active",
        TenantEmailConnection.encrypted_refresh_token.isnot(None),
    ).first() is not None
