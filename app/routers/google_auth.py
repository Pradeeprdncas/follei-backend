"""Public Google identity auth that also connects and syncs Workspace data."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.core.security import create_access_token, hash_password
from app.models.integrations.oauth_connection import OAuthLoginExchange
from app.models.tenancy import Tenant, User
from app.schemas.api_envelope import api_envelope
from app.services.flows.service import ensure_default_flow, ensure_tenant_workflow_runtime
from app.services.integrations.google_workspace import (
    DEFAULT_RESOURCES,
    GMAIL_COMMUNICATION_SCOPES,
    RESOURCE_SCOPES,
    GoogleWorkspaceError,
    GoogleWorkspaceOAuthService,
)
from app.services.integrations.oauth_security import state_hash


router = APIRouter(prefix="/api/v1/auth/google", tags=["Google authentication"])
_settings = get_settings()
_EXCHANGE_TTL_SECONDS = 120
_TOKEN_EXPIRES_IN = 3600


class GoogleAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_name: str | None = Field(default=None, min_length=1, max_length=200)


class GoogleAuthExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange_code: str = Field(min_length=20, max_length=512)


def _full_name(identity: dict) -> str:
    value = str(identity.get("name") or "").strip()
    if value:
        return value[:200]
    parts = [str(identity.get(key) or "").strip() for key in ("given_name", "family_name")]
    value = " ".join(item for item in parts if item)
    if value:
        return value[:200]
    return str(identity.get("email") or "Google user").split("@", 1)[0][:200]


def _account_for_identity(db: Session, *, identity: dict, requested_tenant_name: str | None) -> tuple[User, bool]:
    email = str(identity.get("email") or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        if user.is_active is False or user.status == "inactive":
            raise GoogleWorkspaceError("Follei user is inactive")
        return user, False

    full_name = _full_name(identity)
    first_name, _, last_name = full_name.partition(" ")
    hosted_domain = str(identity.get("hd") or "").strip()
    tenant_name = (
        (requested_tenant_name or "").strip()
        or hosted_domain
        or f"{full_name}'s workspace"
    )[:200]
    slug_base = re.sub(r"[^a-z0-9]+", "-", tenant_name.lower()).strip("-") or "workspace"
    tenant = Tenant(
        id=uuid4(),
        name=tenant_name,
        domain=None,
        slug=f"{slug_base}-{secrets.token_hex(4)}",
        status="active",
        is_active=True,
        industry_pack_activated=False,
        timezone="Asia/Kolkata",
        auto_reply_enabled=False,
        lead_contact_requirement=1,
    )
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=email,
        # Google-created accounts have no usable local password. Password reset
        # can explicitly establish one later.
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        role="admin",
        status="active",
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    ensure_default_flow(db, tenant.id)
    ensure_tenant_workflow_runtime(db, tenant.id)
    return user, True


def _publish_sync_jobs(connection, run, jobs) -> None:
    ensure_topics()
    producer = get_producer()
    for job in jobs:
        producer.send(
            _settings.KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC,
            key=str(job.id),
            value={
                "job_id": str(job.id),
                "run_id": str(run.id),
                "source_id": str(run.source_id),
                "connection_id": str(connection.id),
                "tenant_id": str(connection.tenant_id),
                "resource": (job.payload or {}).get("resource"),
            },
        )
    producer.flush()


@router.post("/start")
def google_auth_start(payload: GoogleAuthStartRequest, db: Session = Depends(get_db)):
    """Start public sign-in/signup and request Workspace plus Gmail communication consent."""
    resources = list(DEFAULT_RESOURCES)
    try:
        authorization_url = GoogleWorkspaceOAuthService().create_identity_authorization_url(
            db,
            resources=resources,
            tenant_name=payload.tenant_name,
        )
    except GoogleWorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return api_envelope({
        "authorization_url": authorization_url,
        "resources": resources,
        "scopes": [
            *(RESOURCE_SCOPES[item] for item in resources),
            *GMAIL_COMMUNICATION_SCOPES,
        ],
        "gmail_communication": {
            "requested": True,
            "capabilities": ["send", "reply", "read_inbound"],
        },
    })


@router.get("/callback", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def google_auth_callback(
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Provider callback; redirect a short-lived exchange code to the frontend."""
    safe_error = "access_denied" if error == "access_denied" else "oauth_failed"
    try:
        if error or not state or not code:
            raise GoogleWorkspaceError("Google authorization was not completed")
        service = GoogleWorkspaceOAuthService()
        oauth_state, token_data, identity = await service.complete_identity_authorization(
            db,
            state=state,
            code=code,
        )
        user, is_new_user = _account_for_identity(
            db,
            identity=identity,
            requested_tenant_name=str(oauth_state.metadata_.get("tenant_name") or "") or None,
        )
        connection, run, jobs = service.persist_workspace_connection(
            db,
            tenant_id=user.tenant_id,
            token_data=token_data,
            identity=identity,
            resources=list(oauth_state.metadata_.get("resources") or DEFAULT_RESOURCES),
        )
        email_connection = service.persist_gmail_communication_connection(
            db,
            tenant_id=user.tenant_id,
            token_data=token_data,
            identity=identity,
            sender_name=getattr(user, "full_name", None) or _full_name(identity),
            auto_reply_enabled=True,
            allow_inbound_lead_creation=True,
            campaign_enabled=True,
        )
        _publish_sync_jobs(connection, run, jobs)

        exchange_code = secrets.token_urlsafe(48)
        db.add(OAuthLoginExchange(
            tenant_id=user.tenant_id,
            user_id=user.id,
            provider="google",
            code_hash=state_hash(exchange_code),
            expires_at=datetime.utcnow() + timedelta(seconds=_EXCHANGE_TTL_SECONDS),
        ))
        db.commit()
        query = {
            "exchange_code": exchange_code,
            "expires_in": _EXCHANGE_TTL_SECONDS,
            "is_new_user": str(is_new_user).lower(),
            "connection_id": str(connection.id),
            "email_connection_id": str(email_connection.id),
            "gmail_communication": "connected",
            "run_id": str(run.id),
            "resources": ",".join(oauth_state.metadata_.get("resources") or DEFAULT_RESOURCES),
        }
    except Exception as exc:
        db.rollback()
        logger.warning("Google identity OAuth callback failed: {}", type(exc).__name__)
        query = {"error": safe_error}

    callback_url = f"{_settings.FRONTEND_BASE_URL.rstrip('/')}/auth/callback"
    return RedirectResponse(
        url=f"{callback_url}?{urlencode(query)}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/exchange")
def exchange_google_login(payload: GoogleAuthExchangeRequest, db: Session = Depends(get_db)):
    """Consume the popup code once and issue the normal Follei token/session shape."""
    row = db.query(OAuthLoginExchange).filter(
        OAuthLoginExchange.code_hash == state_hash(payload.exchange_code),
        OAuthLoginExchange.provider == "google",
    ).with_for_update().first()
    if not row or row.consumed_at or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Google exchange code")
    user = db.get(User, row.user_id)
    if not user or user.is_active is False or user.status == "inactive":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    row.consumed_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()
    db.commit()
    return {
        "access_token": create_access_token(user.id, user.tenant_id),
        "refresh_token": create_access_token(user.id, user.tenant_id),
        "token_type": "bearer",
        "expires_in": _TOKEN_EXPIRES_IN,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name or f"{user.first_name} {user.last_name}".strip(),
            "tenant_id": str(user.tenant_id),
            "roles": [user.role] if user.role else [],
        },
    }
