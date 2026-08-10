"""Tenant-scoped email connection management."""
from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.integrations.email_connection import TenantEmailConnection
from app.schemas.email_connection import (
    EmailConnectionCreate,
    EmailConnectionResponse,
    EmailConnectionUpdate,
    GmailOAuthStartRequest,
    GmailOAuthStartResponse,
)
from app.services.communications.email_connections import encrypt_secret
from app.services.communications.connection_verification import (
    ProviderVerificationError,
    verify_brevo_email,
    verify_gmail_app_password,
)
from app.services.communications.gmail_oauth import GmailOAuthError, GmailOAuthService

router = APIRouter(prefix="/api/email-connections", tags=["Onboarding - email connections"])


def _oauth_result_url(target: str, **params: str) -> str:
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{urlencode(params)}"


def _response(row: TenantEmailConnection) -> EmailConnectionResponse:
    return EmailConnectionResponse(
        id=str(row.id),
        provider=row.provider,
        email_address=row.email_address,
        sender_name=row.sender_name,
        enabled=bool(row.enabled),
        verified=bool(row.verified),
        auto_reply_enabled=bool(row.auto_reply_enabled),
        allow_inbound_lead_creation=bool(row.allow_inbound_lead_creation),
        campaign_enabled=bool(row.campaign_enabled),
        status=row.status,
        has_api_key=bool(row.encrypted_api_key),
        has_app_password=bool(row.encrypted_app_password),
        auth_type=row.auth_type or ("app_password" if row.provider == "gmail" else "api_key"),
        oauth_connected=bool(row.auth_type == "oauth" and row.encrypted_refresh_token),
        inbound_ready=(
            row.provider != "gmail"
            or (row.auth_type == "oauth" and row.gmail_history_id is not None)
            or (row.auth_type != "oauth" and row.imap_last_uid is not None)
        ),
        last_polled_at=row.last_polled_at,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _owned(db: Session, tenant_id: str, connection_id: UUID) -> TenantEmailConnection:
    row = db.query(TenantEmailConnection).filter(
        TenantEmailConnection.id == connection_id,
        TenantEmailConnection.tenant_id == UUID(tenant_id),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Email connection not found")
    return row


@router.get("", response_model=list[EmailConnectionResponse])
def list_email_connections(
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    rows = db.query(TenantEmailConnection).filter(
        TenantEmailConnection.tenant_id == UUID(tenant_id)
    ).order_by(TenantEmailConnection.created_at.asc()).all()
    return [_response(row) for row in rows]


@router.post("", response_model=EmailConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_email_connection(
    payload: EmailConnectionCreate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    row = TenantEmailConnection(
        tenant_id=UUID(tenant_id),
        provider=payload.provider,
        email_address=str(payload.email_address).strip().lower(),
        sender_name=payload.sender_name.strip(),
        encrypted_api_key=encrypt_secret(payload.api_key),
        encrypted_app_password=encrypt_secret(payload.app_password),
        auth_type="app_password" if payload.provider == "gmail" else "api_key",
        imap_host="imap.gmail.com" if payload.provider == "gmail" else None,
        smtp_host="smtp.gmail.com" if payload.provider == "gmail" else None,
        smtp_port=465 if payload.provider == "gmail" else None,
        auto_reply_enabled=payload.auto_reply_enabled if payload.provider == "gmail" else False,
        allow_inbound_lead_creation=payload.allow_inbound_lead_creation if payload.provider == "gmail" else False,
        campaign_enabled=payload.campaign_enabled,
        status="configured",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This tenant already has that provider/address connection") from exc
    db.refresh(row)
    return _response(row)


@router.post(
    "/gmail/oauth/start",
    response_model=GmailOAuthStartResponse,
    tags=["email-connections"],
)
def start_gmail_oauth(
    payload: GmailOAuthStartRequest,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    user_id: str = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
) -> GmailOAuthStartResponse:
    service = GmailOAuthService()
    try:
        authorization_url = service.create_authorization_url(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            expected_email=str(payload.email_address).strip().lower() if payload.email_address else None,
            sender_name=payload.sender_name,
            auto_reply_enabled=payload.auto_reply_enabled,
            allow_inbound_lead_creation=payload.allow_inbound_lead_creation,
            campaign_enabled=payload.campaign_enabled,
        )
    except GmailOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GmailOAuthStartResponse(
        authorization_url=authorization_url,
        expires_in=max(120, min(get_settings().GMAIL_OAUTH_STATE_TTL_SECONDS, 1800)),
    )


@router.get("/gmail/oauth/callback", include_in_schema=True)
async def gmail_oauth_callback(
    state_value: str | None = Query(default=None, alias="state"),
    code: str | None = Query(default=None),
    google_error: str | None = Query(default=None, alias="error"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    target = settings.GMAIL_OAUTH_SUCCESS_URL
    if google_error or not state_value or not code:
        return RedirectResponse(_oauth_result_url(
            target,
            gmail_oauth="error",
            reason="authorization_denied",
        ))
    try:
        row = await GmailOAuthService().complete_authorization(db, state=state_value, code=code)
    except GmailOAuthError:
        return RedirectResponse(_oauth_result_url(
            target,
            gmail_oauth="error",
            reason="connection_failed",
        ))
    return RedirectResponse(_oauth_result_url(
        target,
        gmail_oauth="connected",
        email=row.email_address,
    ))


@router.patch("/{connection_id}", response_model=EmailConnectionResponse)
def update_email_connection(
    connection_id: UUID,
    payload: EmailConnectionUpdate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    row = _owned(db, tenant_id, connection_id)
    changes = payload.model_dump(exclude_unset=True)
    api_key = changes.pop("api_key", None)
    app_password = changes.pop("app_password", None)
    requested_email = changes.pop("email_address", None)
    requested_enabled = changes.pop("enabled", None)

    if requested_email is not None:
        clean_email = str(requested_email).strip().lower()
        if row.provider == "gmail" and row.auth_type == "oauth" and clean_email != row.email_address:
            raise HTTPException(
                status_code=409,
                detail="A Gmail OAuth address cannot be renamed. Use Connect Google for the new mailbox.",
            )
        row.email_address = clean_email

    for key, value in changes.items():
        if value is not None:
            setattr(row, key, value.strip() if isinstance(value, str) else value)
    if api_key:
        row.encrypted_api_key = encrypt_secret(api_key)
    if app_password:
        row.encrypted_app_password = encrypt_secret(app_password)
    if api_key or app_password or requested_email is not None:
        row.verified = False
        row.status = "configured"

    if requested_enabled is not None:
        if requested_enabled and row.auth_type == "oauth" and not row.encrypted_refresh_token:
            raise HTTPException(
                status_code=409,
                detail="Connect this Gmail address with Google before turning the service on.",
            )
        row.enabled = requested_enabled
        if not requested_enabled:
            row.status = "paused"
        elif row.auth_type == "oauth":
            row.status = "active"
        else:
            row.status = "configured"
    elif row.status == "error" and row.enabled:
        row.status = "active" if row.auth_type == "oauth" else "configured"

    row.last_error = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That email address is already connected to this or another tenant.",
        ) from exc
    db.refresh(row)
    return _response(row)


@router.post("/{connection_id}/verify", response_model=EmailConnectionResponse)
async def verify_email_connection(
    connection_id: UUID,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    """Verify credentials and sender ownership with the provider before use."""
    row = _owned(db, tenant_id, connection_id)
    if row.provider == "gmail" and row.auth_type == "oauth":
        if not row.encrypted_refresh_token:
            raise HTTPException(status_code=422, detail="Complete Google OAuth before verification")
        # OAuth callback already confirms /users/me/profile and binds its email.
        row.verified = True
        row.status = "active"
        row.last_error = None
    else:
        try:
            if row.provider == "gmail":
                await asyncio.to_thread(verify_gmail_app_password, row)
            elif row.provider == "brevo":
                await verify_brevo_email(row)
            else:
                raise ProviderVerificationError(f"Unsupported email provider {row.provider}")
        except ProviderVerificationError as exc:
            row.verified = False
            row.status = "verification_failed"
            row.last_error = str(exc)[:2000]
            db.commit()
            raise HTTPException(status_code=422, detail=row.last_error) from exc
        row.verified = True
        row.status = "active"
        row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _response(row)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_email_connection(
    connection_id: UUID,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    row = _owned(db, tenant_id, connection_id)
    if row.provider == "gmail" and row.auth_type == "oauth":
        await GmailOAuthService().revoke_connection(db, row)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    row.enabled = False
    row.status = "disconnected"
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
