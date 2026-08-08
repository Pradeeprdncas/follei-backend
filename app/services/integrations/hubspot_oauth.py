"""Tenant-scoped HubSpot OAuth using the canonical CRM connection table."""
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.crm import TenantCRMConnection
from app.models.integrations.oauth_connection import IntegrationOAuthState
from app.services.communications.email_connections import decrypt_secret, encrypt_secret
from app.services.crm.sync import encrypt_crm_token
from app.services.integrations.oauth_security import new_pkce, state_hash


HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v3/token"
HUBSPOT_SCOPES = (
    "oauth", "crm.objects.contacts.read", "crm.objects.companies.read", "crm.objects.deals.read",
)


class HubSpotOAuthError(RuntimeError):
    pass


class HubSpotOAuthService:
    def __init__(self):
        self.settings = get_settings()

    def authorization_url(self, db: Session, *, tenant_id: str, user_id: str) -> str:
        if not self.settings.HUBSPOT_CLIENT_ID or not self.settings.HUBSPOT_CLIENT_SECRET:
            raise HubSpotOAuthError("HubSpot OAuth client ID/secret are not configured")
        state, verifier, _ = new_pkce()
        db.add(IntegrationOAuthState(
            tenant_id=UUID(tenant_id), user_id=UUID(user_id), provider="hubspot",
            state_hash=state_hash(state), encrypted_code_verifier=encrypt_secret(verifier),
            metadata_={"scopes": list(HUBSPOT_SCOPES)}, expires_at=datetime.utcnow() + timedelta(minutes=10),
        ))
        db.commit()
        return f"{HUBSPOT_AUTHORIZE_URL}?{urlencode({'client_id': self.settings.HUBSPOT_CLIENT_ID, 'redirect_uri': self.settings.HUBSPOT_REDIRECT_URI, 'scope': ' '.join(HUBSPOT_SCOPES), 'state': state})}"

    async def complete(self, db: Session, *, state: str, code: str) -> TenantCRMConnection:
        oauth_state = db.query(IntegrationOAuthState).filter(
            IntegrationOAuthState.state_hash == state_hash(state), IntegrationOAuthState.provider == "hubspot",
        ).first()
        if not oauth_state or oauth_state.consumed_at or oauth_state.expires_at < datetime.utcnow():
            raise HubSpotOAuthError("OAuth state is invalid, expired, or already used")
        oauth_state.consumed_at = datetime.utcnow()
        db.commit()
        token_data = await self._token_request({
            "grant_type": "authorization_code", "client_id": self.settings.HUBSPOT_CLIENT_ID,
            "client_secret": self.settings.HUBSPOT_CLIENT_SECRET, "redirect_uri": self.settings.HUBSPOT_REDIRECT_URI,
            "code": code,
        })
        token = str(token_data.get("access_token") or "")
        refresh = str(token_data.get("refresh_token") or "")
        if not token or not refresh:
            raise HubSpotOAuthError("HubSpot did not return renewable credentials")
        connection = db.query(TenantCRMConnection).filter_by(tenant_id=oauth_state.tenant_id, provider="hubspot").first()
        if connection is None:
            connection = TenantCRMConnection(tenant_id=oauth_state.tenant_id, provider="hubspot", sync_cursor={})
            db.add(connection)
        connection.status = "active"
        connection.auth_type = "oauth"
        connection.encrypted_access_token = encrypt_crm_token(token)
        connection.encrypted_refresh_token = encrypt_secret(refresh)
        connection.access_token_expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in") or 1800))
        connection.external_account_id = str(token_data.get("hub_id") or token_data.get("hubId") or "") or connection.external_account_id
        connection.scopes = str(token_data.get("scope") or " ".join(HUBSPOT_SCOPES)).split()
        connection.last_error = None
        db.commit()
        db.refresh(connection)
        return connection

    async def valid_access_token(self, db: Session, connection: TenantCRMConnection) -> None:
        if connection.auth_type != "oauth" or not connection.encrypted_refresh_token:
            return
        if connection.access_token_expires_at and connection.access_token_expires_at > datetime.utcnow() + timedelta(minutes=2):
            return
        token_data = await self._token_request({
            "grant_type": "refresh_token", "client_id": self.settings.HUBSPOT_CLIENT_ID,
            "client_secret": self.settings.HUBSPOT_CLIENT_SECRET,
            "refresh_token": decrypt_secret(connection.encrypted_refresh_token),
        })
        token = str(token_data.get("access_token") or "")
        if not token:
            raise HubSpotOAuthError("HubSpot token refresh returned no access token")
        connection.encrypted_access_token = encrypt_crm_token(token)
        if token_data.get("refresh_token"):
            connection.encrypted_refresh_token = encrypt_secret(str(token_data["refresh_token"]))
        connection.access_token_expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in") or 1800))
        db.commit()

    async def _token_request(self, data: dict[str, str]) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(HUBSPOT_TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if response.status_code != 200:
            raise HubSpotOAuthError(f"HubSpot token request failed ({response.status_code})")
        return response.json()
