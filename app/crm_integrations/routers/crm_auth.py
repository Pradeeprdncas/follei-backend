from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.crm_integrations.config import settings
from app.crm_integrations.database import get_db
from app.crm_integrations.models.crm_connection import CRMConnection
from app.crm_integrations.schemas.crm_connection import CRMConnectionCreate, CRMConnectionRead
from app.crm_integrations.schemas.crm_provider import CRMProviderResponse, CRMProvidersResponse
from app.crm_integrations.routers.crm import save_connection
from app.crm_integrations.security import require_api_token
from app.crm_integrations.services.crm_registry import CRMRegistryEntry, list_crm_registry
from app.crm_integrations.services.oauth_service import OAuthService
from app.crm_integrations.services.token_service import TokenService


router = APIRouter(prefix="/api/crm/auth", tags=["CRM"])
alias_router = APIRouter(prefix="/api/crm", tags=["CRM"])
oauth_service = OAuthService()
token_service = TokenService()


class OAuthCallbackPayload(BaseModel):
    code: str
    workspace_name: str
    login_email: str
    sync_scope: str = "contacts"
    allow_collab: bool = True
    auto_sync: bool = True


def frontend_redirect(**params):
    return_path = settings.frontend_crm_return_path
    if not return_path.startswith("/"):
        return_path = f"/{return_path}"
    return RedirectResponse(f"{settings.frontend_base_url}{return_path}?{urlencode(params)}")


def token_expires_at(token_response: dict[str, str | int | None]) -> datetime | None:
    expires_in = token_response.get("expires_in")
    if not expires_in:
        return None
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def build_provider_response(provider: CRMRegistryEntry, connected_providers: set[str], workspace_name: str | None = None, login_email: str | None = None, sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True) -> CRMProviderResponse:
    connected = provider.id in connected_providers
    enabled = not provider.oauth or oauth_service.is_provider_configured(provider.id)
    status = "connected" if connected else "available" if enabled else "not_configured"
    login_url = None
    if enabled and provider.oauth and workspace_name and login_email:
        login_url = oauth_service.build_authorization_url(provider=provider.id, workspace_name=workspace_name, login_email=login_email, sync_scope=sync_scope, allow_collab=allow_collab, auto_sync=auto_sync)
    return CRMProviderResponse(id=provider.id, name=provider.name, provider=provider.provider, description=provider.description, category=provider.category, icon=provider.icon, logo=provider.logo, website=provider.website, enabled=enabled, oauth=provider.oauth, connected=connected, status=status, connect_url=f"/api/crm/{provider.id}/connect", login_url_endpoint=f"/api/crm/auth/{provider.id}/login-url", supports=provider.supports, features=provider.features, default_scopes=provider.default_scopes or None, login_url=login_url)


@router.get("/providers", response_model=CRMProvidersResponse)
def list_auth_providers(workspace_name: str | None = Query(default=None, min_length=1), login_email: str | None = Query(default=None, min_length=3), sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True, db: Session = Depends(get_db)):
    connected = {row.provider for row in db.query(CRMConnection).filter(CRMConnection.status == "connected").all()}
    crms = [build_provider_response(provider=provider, connected_providers=connected, workspace_name=workspace_name, login_email=login_email, sync_scope=sync_scope, allow_collab=allow_collab, auto_sync=auto_sync) for provider in list_crm_registry()]
    return CRMProvidersResponse(crms=crms)


@router.get("/{provider}/login-url")
def get_login_url(provider: str, workspace_name: str = Query(..., min_length=1), login_email: str = Query(..., min_length=3), sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True, authorized: bool = Depends(require_api_token)):
    url = oauth_service.build_authorization_url(provider=provider, workspace_name=workspace_name, login_email=login_email, sync_scope=sync_scope, allow_collab=allow_collab, auto_sync=auto_sync)
    if not url:
        raise HTTPException(status_code=404, detail="OAuth provider not configured")
    return {"provider": provider, "login_url": url}


def provider_login_redirect(provider: str, workspace_name: str, login_email: str, sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True, authorized: bool = Depends(require_api_token)):
    url = oauth_service.build_authorization_url(provider=provider, workspace_name=workspace_name, login_email=login_email, sync_scope=sync_scope, allow_collab=allow_collab, auto_sync=auto_sync)
    if not url:
        raise HTTPException(status_code=404, detail="OAuth provider not configured")
    return RedirectResponse(url)


@router.get("/{provider}/connect")
def redirect_to_provider_login(provider: str, workspace_name: str = Query(..., min_length=1), login_email: str = Query(..., min_length=3), sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True, authorized: bool = Depends(require_api_token)):
    return provider_login_redirect(provider, workspace_name, login_email, sync_scope, allow_collab, auto_sync)


@alias_router.get("/{provider}/connect")
def redirect_to_provider_login_alias(provider: str, workspace_name: str = Query(..., min_length=1), login_email: str = Query(..., min_length=3), sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True, authorized: bool = Depends(require_api_token)):
    return provider_login_redirect(provider, workspace_name, login_email, sync_scope, allow_collab, auto_sync)


@router.post("/{provider}/callback", response_model=CRMConnectionRead)
async def oauth_callback_post(provider: str, payload: OAuthCallbackPayload, db: Session = Depends(get_db), authorized: bool = Depends(require_api_token)):
    token_response = await oauth_service.exchange_code_for_token(provider, payload.code)
    refresh_token = token_response.get("refresh_token")
    connection_payload = CRMConnectionCreate(provider=provider, workspace_name=payload.workspace_name, login_email=payload.login_email, credential=token_response["access_token"], sync_scope=payload.sync_scope, allow_collab=payload.allow_collab, auto_sync=payload.auto_sync)
    encrypted_refresh_token = token_service.encrypt_token(str(refresh_token)) if refresh_token else None
    return save_connection(connection_payload, db, encrypted_refresh_token=encrypted_refresh_token)


@router.get("/{provider}/callback")
async def oauth_callback_get(provider: str, code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    if error:
        return frontend_redirect(provider=provider, status="error", message=error)
    if not code or not state:
        return frontend_redirect(provider=provider, status="error", message="missing_code")
    try:
        state_payload = oauth_service.read_state(state)
        if state_payload["provider"] != provider:
            raise ValueError("OAuth provider mismatch")
        token_response = await oauth_service.exchange_code_for_token(provider, code)
    except ValueError as exc:
        return frontend_redirect(provider=provider, status="error", message=str(exc))
    now_connection = db.query(CRMConnection).filter(CRMConnection.provider == provider).first()
    access_token = token_service.encrypt_token(str(token_response["access_token"]))
    refresh_token = token_response.get("refresh_token")
    expires_at = token_expires_at(token_response)
    if now_connection:
        now_connection.workspace_name = str(state_payload["workspace_name"])
        now_connection.login_email = str(state_payload["login_email"])
        now_connection.encrypted_access_token = access_token
        now_connection.encrypted_refresh_token = token_service.encrypt_token(str(refresh_token)) if refresh_token else None
        now_connection.token_expires_at = expires_at
        now_connection.sync_scope = str(state_payload["sync_scope"])
        now_connection.allow_collab = bool(state_payload["allow_collab"])
        now_connection.auto_sync = bool(state_payload["auto_sync"])
        now_connection.status = "connected"
        connection = now_connection
    else:
        connection = CRMConnection(
            provider=provider,
            workspace_name=str(state_payload["workspace_name"]),
            login_email=str(state_payload["login_email"]),
            encrypted_access_token=access_token,
            encrypted_refresh_token=token_service.encrypt_token(str(refresh_token)) if refresh_token else None,
            token_expires_at=expires_at,
            sync_scope=str(state_payload["sync_scope"]),
            allow_collab=bool(state_payload["allow_collab"]),
            auto_sync=bool(state_payload["auto_sync"]),
            status="connected",
        )
        db.add(connection)
    db.commit()
    db.refresh(connection)
    return frontend_redirect(provider=provider, connected=provider, status="connected", connection_id=connection.id)
