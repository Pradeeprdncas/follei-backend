import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.crm_integrations.config import settings
from app.crm_integrations.services.crm_registry import get_crm_provider
from app.crm_integrations.utils.encryption import EncryptionService


@dataclass(frozen=True)
class CRMProviderOAuthConfig:
    name: str
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str
    scope: str
    extra_params: dict[str, str] | None = None


class OAuthService:
    def __init__(self):
        self.state_crypto = EncryptionService(settings.encryption_key)

    def build_authorization_url(self, provider: str, workspace_name: str, login_email: str, sync_scope: str = "contacts", allow_collab: bool = True, auto_sync: bool = True) -> str | None:
        redirect_uri = f"{settings.api_base_url}/api/crm/auth/{provider}/callback"
        oauth_config = self._oauth_config(provider)
        if not oauth_config:
            return None
        state = self.create_state(provider=provider, workspace_name=workspace_name, login_email=login_email, sync_scope=sync_scope, allow_collab=allow_collab, auto_sync=auto_sync)
        query = urlencode({"client_id": oauth_config.client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": oauth_config.scope, "state": state, **(oauth_config.extra_params or {})})
        return f"{oauth_config.authorize_url}?{query}"

    def create_state(self, provider: str, workspace_name: str, login_email: str, sync_scope: str, allow_collab: bool, auto_sync: bool) -> str:
        payload = {"provider": provider, "workspace_name": workspace_name, "login_email": login_email, "sync_scope": sync_scope, "allow_collab": allow_collab, "auto_sync": auto_sync, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
        return self.state_crypto.encrypt(json.dumps(payload))

    def read_state(self, state: str) -> dict[str, str | bool]:
        payload = json.loads(self.state_crypto.decrypt(state))
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        if expires_at < datetime.now(timezone.utc):
            raise ValueError("OAuth state expired")
        return payload

    async def exchange_code_for_token(self, provider: str, code: str) -> dict[str, str | int | None]:
        oauth_config = self._oauth_config(provider)
        if not oauth_config:
            raise ValueError("OAuth provider not configured")
        if oauth_config.client_secret:
            redirect_uri = f"{settings.api_base_url}/api/crm/auth/{provider}/callback"
            payload = {"grant_type": "authorization_code", "client_id": oauth_config.client_id, "client_secret": oauth_config.client_secret, "redirect_uri": redirect_uri, "code": code}
            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    response = await client.post(oauth_config.token_url, data=payload, headers={"Accept": "application/json"})
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPError as exc:
                    raise ValueError(f"OAuth token exchange failed for {provider}") from exc
        raise ValueError("OAuth client secret not configured")

    def _oauth_config(self, provider: str) -> CRMProviderOAuthConfig | None:
        provider_config = get_crm_provider(provider)
        if not provider_config or not provider_config.oauth:
            return None
        client_id = str(getattr(settings, provider_config.client_id_attr or "", "") or "")
        client_secret = str(getattr(settings, provider_config.client_secret_attr or "", "") or "")
        scope = " ".join(provider_config.default_scopes)
        if not client_id or not provider_config.authorize_url or not provider_config.token_url:
            return None
        return CRMProviderOAuthConfig(name=provider_config.name, client_id=client_id, client_secret=client_secret, authorize_url=provider_config.authorize_url, token_url=provider_config.token_url, scope=scope, extra_params=provider_config.extra_params)

    def is_provider_configured(self, provider: str) -> bool:
        config = self._oauth_config(provider)
        return bool(config and config.client_secret)
