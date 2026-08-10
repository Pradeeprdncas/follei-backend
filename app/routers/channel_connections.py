"""Tenant-scoped SMS, WhatsApp, and voice connection management."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.integrations.channel_connection import ChannelComplianceAcknowledgement, TenantChannelConnection
from app.schemas.channel_connection import ChannelComplianceUpdate, ChannelConnectionCreate, ChannelConnectionResponse
from app.services.communications.connection_verification import ProviderVerificationError, verify_channel
from app.services.communications.email_connections import encrypt_secret

router = APIRouter(prefix="/api/channel-connections", tags=["Onboarding - channel connections"])


def _owned(db: Session, tenant_id: str, connection_id: UUID) -> TenantChannelConnection:
    row = db.query(TenantChannelConnection).filter(
        TenantChannelConnection.id == connection_id,
        TenantChannelConnection.tenant_id == UUID(tenant_id),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Channel connection not found")
    return row


def _compliance(db: Session, row: TenantChannelConnection) -> ChannelComplianceAcknowledgement | None:
    return db.query(ChannelComplianceAcknowledgement).filter_by(connection_id=row.id).first()


def _compliance_ready(record: ChannelComplianceAcknowledgement | None) -> bool:
    return bool(record and record.policy_version and record.opt_in_acknowledged and record.stop_help_acknowledged)


def _response(db: Session, row: TenantChannelConnection) -> ChannelConnectionResponse:
    return ChannelConnectionResponse(
        id=str(row.id), channel=row.channel, provider=row.provider, identity=row.identity,
        provider_account_id=row.provider_account_id, enabled=bool(row.enabled), verified=bool(row.verified),
        inbound_enabled=bool(row.inbound_enabled), campaign_enabled=bool(row.campaign_enabled),
        compliance_ready=_compliance_ready(_compliance(db, row)), status=row.status,
        verified_at=row.verified_at, last_verified_at=row.last_verified_at, last_error=row.last_error,
        created_at=row.created_at, updated_at=row.updated_at,
    )


async def _verify_and_save(db: Session, row: TenantChannelConnection) -> None:
    row.last_verified_at = datetime.utcnow()
    try:
        result = await verify_channel(row)
    except ProviderVerificationError as exc:
        row.verified = False
        row.status = "verification_failed"
        row.last_error = str(exc)[:2000]
    else:
        row.verified = True
        row.status = "active" if row.enabled else "paused"
        row.verified_at = datetime.utcnow()
        row.last_error = None
        row.verification_metadata = result.metadata
    db.commit()
    db.refresh(row)


@router.get("", response_model=list[ChannelConnectionResponse])
def list_channel_connections(tenant_id: str = Depends(get_authenticated_tenant_id), db: Session = Depends(get_db)):
    rows = db.query(TenantChannelConnection).filter_by(tenant_id=UUID(tenant_id)).order_by(TenantChannelConnection.created_at).all()
    return [_response(db, row) for row in rows]


@router.post("", response_model=ChannelConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_connection(
    payload: ChannelConnectionCreate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    user_id: str = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
):
    row = TenantChannelConnection(
        tenant_id=UUID(tenant_id), channel=payload.channel, provider=payload.provider,
        identity=payload.identity.strip(), provider_account_id=payload.provider_account_id,
        encrypted_account_sid=encrypt_secret(payload.account_sid),
        encrypted_auth_token=encrypt_secret(payload.auth_token), encrypted_api_key=encrypt_secret(payload.api_key),
        inbound_enabled=payload.inbound_enabled, campaign_enabled=payload.campaign_enabled,
    )
    db.add(row)
    try:
        db.flush()
        if payload.compliance_policy_version:
            db.add(ChannelComplianceAcknowledgement(
                tenant_id=row.tenant_id, connection_id=row.id, channel=row.channel,
                policy_version=payload.compliance_policy_version,
                opt_in_acknowledged=payload.opt_in_acknowledged,
                stop_help_acknowledged=payload.stop_help_acknowledged,
                acknowledged_by=UUID(user_id),
                acknowledged_at=datetime.utcnow() if payload.opt_in_acknowledged and payload.stop_help_acknowledged else None,
            ))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This channel identity is already connected for the tenant") from exc
    db.refresh(row)
    await _verify_and_save(db, row)
    return _response(db, row)


@router.post("/{connection_id}/verify", response_model=ChannelConnectionResponse)
async def verify_channel_connection(
    connection_id: UUID,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
):
    row = _owned(db, tenant_id, connection_id)
    await _verify_and_save(db, row)
    if not row.verified:
        raise HTTPException(status_code=422, detail=row.last_error or "Provider verification failed")
    return _response(db, row)


@router.post("/{connection_id}/compliance", response_model=ChannelConnectionResponse)
def acknowledge_channel_compliance(
    connection_id: UUID,
    payload: ChannelComplianceUpdate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    user_id: str = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
):
    row = _owned(db, tenant_id, connection_id)
    if row.channel not in {"sms", "whatsapp"}:
        raise HTTPException(status_code=422, detail="Compliance acknowledgement applies to SMS and WhatsApp connections")
    if payload.campaign_enabled and not (payload.opt_in_acknowledged and payload.stop_help_acknowledged):
        raise HTTPException(status_code=422, detail="Campaign messaging requires opt-in and STOP/HELP acknowledgement")
    record = _compliance(db, row) or ChannelComplianceAcknowledgement(
        tenant_id=row.tenant_id, connection_id=row.id, channel=row.channel,
    )
    record.policy_version = payload.policy_version
    record.opt_in_acknowledged = payload.opt_in_acknowledged
    record.stop_help_acknowledged = payload.stop_help_acknowledged
    record.acknowledged_by = UUID(user_id)
    record.acknowledged_at = datetime.utcnow() if payload.opt_in_acknowledged and payload.stop_help_acknowledged else None
    row.campaign_enabled = payload.campaign_enabled and _compliance_ready(record)
    db.add(record)
    db.commit()
    db.refresh(row)
    return _response(db, row)
