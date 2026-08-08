"""Generalized Google Workspace OAuth and incremental resource API adapter."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.integrations.oauth_connection import GoogleWorkspaceConnection, IntegrationOAuthState
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.services.communications.email_connections import decrypt_secret, encrypt_secret
from app.services.integrations.oauth_security import new_pkce, state_hash


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
RESOURCE_SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.readonly",
    "drive": "https://www.googleapis.com/auth/drive.readonly",
    "calendar": "https://www.googleapis.com/auth/calendar.readonly",
    "contacts": "https://www.googleapis.com/auth/contacts.readonly",
}
DEFAULT_RESOURCES = tuple(RESOURCE_SCOPES)


class GoogleWorkspaceError(RuntimeError):
    pass


class GoogleWorkspaceOAuthService:
    def __init__(self):
        self.settings = get_settings()

    def create_authorization_url(self, db: Session, *, tenant_id: str, user_id: str, resources: list[str]) -> str:
        selected = list(dict.fromkeys(resources))
        invalid = sorted(set(selected) - set(RESOURCE_SCOPES))
        if invalid or not selected:
            raise GoogleWorkspaceError(f"Invalid Google resources: {invalid or 'none selected'}")
        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise GoogleWorkspaceError("Google OAuth client ID/secret are not configured")
        state, verifier, challenge = new_pkce()
        nonce = secrets.token_urlsafe(24)
        db.add(IntegrationOAuthState(
            tenant_id=UUID(tenant_id), user_id=UUID(user_id), provider="google_workspace",
            state_hash=state_hash(state), encrypted_code_verifier=encrypt_secret(verifier),
            metadata_={"resources": selected, "nonce": nonce},
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        ))
        db.commit()
        scopes = ["openid", "email", "profile", *(RESOURCE_SCOPES[item] for item in selected)]
        query = urlencode({
            "client_id": self.settings.GMAIL_CLIENT_ID,
            "redirect_uri": self.settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI,
            "response_type": "code", "scope": " ".join(scopes), "access_type": "offline",
            "include_granted_scopes": "true", "prompt": "consent", "state": state,
            "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        })
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    async def complete_authorization(self, db: Session, *, state: str, code: str) -> tuple[GoogleWorkspaceConnection, IngestionRun, list[SourceIngestionJob]]:
        row = db.query(IntegrationOAuthState).filter(
            IntegrationOAuthState.state_hash == state_hash(state),
            IntegrationOAuthState.provider == "google_workspace",
        ).first()
        if not row or row.consumed_at or row.expires_at < datetime.utcnow():
            raise GoogleWorkspaceError("OAuth state is invalid, expired, or already used")
        row.consumed_at = datetime.utcnow()
        db.commit()
        token_data = await self._token_request({
            "client_id": self.settings.GMAIL_CLIENT_ID, "client_secret": self.settings.GMAIL_CLIENT_SECRET,
            "code": code, "code_verifier": decrypt_secret(row.encrypted_code_verifier),
            "grant_type": "authorization_code", "redirect_uri": self.settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI,
        })
        access_token = str(token_data.get("access_token") or "")
        identity = await self._verify_identity(token_data, expected_nonce=str(row.metadata_.get("nonce") or ""))
        subject = str(identity.get("sub") or "")
        email = str(identity.get("email") or "").strip().lower()
        if not access_token or not subject or not email or identity.get("email_verified") not in (True, "true"):
            raise GoogleWorkspaceError("Google did not return a verified Workspace identity")

        connection = db.query(GoogleWorkspaceConnection).filter_by(tenant_id=row.tenant_id, provider_account_id=subject).first()
        resources = list(row.metadata_.get("resources") or [])
        source = None
        if connection and connection.source_id:
            source = db.get(KnowledgeSource, connection.source_id)
        if source is None:
            source = KnowledgeSource(
                id=uuid4(), tenant_id=row.tenant_id, name=f"Google Workspace: {email}",
                source_type="google_workspace", status="queued", config={"account": email, "resources": resources},
            )
            db.add(source)
        if connection is None:
            connection = GoogleWorkspaceConnection(
                tenant_id=row.tenant_id, provider_account_id=subject, email_address=email,
                encrypted_access_token=encrypt_secret(access_token), source_id=source.id,
            )
            db.add(connection)
        connection.email_address = email
        connection.source_id = source.id
        connection.status = "active"
        connection.encrypted_access_token = encrypt_secret(access_token)
        refresh = str(token_data.get("refresh_token") or "")
        if refresh:
            connection.encrypted_refresh_token = encrypt_secret(refresh)
        if not connection.encrypted_refresh_token:
            raise GoogleWorkspaceError("Google did not return a refresh token; revoke access and reconnect")
        connection.access_token_expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in") or 3600))
        connection.scopes = str(token_data.get("scope") or "").split()
        connection.enabled_resources = resources
        db.flush()
        run = IngestionRun(id=uuid4(), tenant_id=row.tenant_id, source_id=source.id, status="queued")
        jobs = [
            SourceIngestionJob(
                id=uuid4(), tenant_id=row.tenant_id, run_id=run.id, job_type=f"google_{resource}_sync",
                target=email, status="queued", payload={"connection_id": str(connection.id), "resource": resource},
            )
            for resource in resources
        ]
        db.add_all([run, *jobs])
        db.commit()
        return connection, run, jobs

    async def valid_access_token(self, db: Session, connection: GoogleWorkspaceConnection) -> str:
        if connection.access_token_expires_at and connection.access_token_expires_at > datetime.utcnow() + timedelta(minutes=2):
            return decrypt_secret(connection.encrypted_access_token)
        token_data = await self._token_request({
            "client_id": self.settings.GMAIL_CLIENT_ID, "client_secret": self.settings.GMAIL_CLIENT_SECRET,
            "refresh_token": decrypt_secret(connection.encrypted_refresh_token), "grant_type": "refresh_token",
        })
        token = str(token_data.get("access_token") or "")
        if not token:
            raise GoogleWorkspaceError("Google token refresh returned no access token")
        connection.encrypted_access_token = encrypt_secret(token)
        connection.access_token_expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in") or 3600))
        db.commit()
        return token

    async def fetch_resource(self, token: str, resource: str, cursor: str | None = None, max_pages: int = 10) -> tuple[list[dict], str | None]:
        records: list[dict] = []
        next_page: str | None = None
        final_cursor = cursor
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(max_pages):
                if resource == "gmail":
                    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
                    params = {"maxResults": 100, **({"pageToken": next_page} if next_page else {})}
                elif resource == "drive":
                    url = "https://www.googleapis.com/drive/v3/files"
                    params = {"pageSize": 100, "q": "trashed = false", "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,description)", **({"pageToken": next_page} if next_page else {})}
                elif resource == "calendar":
                    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                    params = {"maxResults": 2500, "singleEvents": "true", **({"pageToken": next_page} if next_page else {}), **({"syncToken": cursor} if cursor and not next_page else {})}
                elif resource == "contacts":
                    url = "https://people.googleapis.com/v1/people/me/connections"
                    params = {"pageSize": 1000, "personFields": "names,emailAddresses,phoneNumbers,organizations", "requestSyncToken": "true", **({"pageToken": next_page} if next_page else {}), **({"syncToken": cursor} if cursor and not next_page else {})}
                else:
                    raise GoogleWorkspaceError(f"Unsupported Google resource: {resource}")
                response = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
                if response.status_code == 410 and cursor:
                    return await self.fetch_resource(token, resource, cursor=None, max_pages=max_pages)
                if response.status_code >= 400:
                    raise GoogleWorkspaceError(f"Google {resource} sync failed ({response.status_code})")
                payload = response.json()
                key = {"gmail": "messages", "drive": "files", "calendar": "items", "contacts": "connections"}[resource]
                records.extend(payload.get(key) or [])
                next_page = payload.get("nextPageToken")
                final_cursor = payload.get("nextSyncToken") or final_cursor
                if not next_page:
                    break
            if resource == "gmail":
                profile = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers={"Authorization": f"Bearer {token}"})
                if profile.status_code == 200:
                    final_cursor = str(profile.json().get("historyId") or final_cursor or "") or None
            elif resource == "drive" and not final_cursor:
                start = await client.get("https://www.googleapis.com/drive/v3/changes/startPageToken", headers={"Authorization": f"Bearer {token}"})
                if start.status_code == 200:
                    final_cursor = start.json().get("startPageToken")
        return records, final_cursor

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=data)
        if response.status_code != 200:
            raise GoogleWorkspaceError(f"Google token request failed ({response.status_code})")
        return response.json()

    async def _verify_identity(self, token_data: dict[str, Any], *, expected_nonce: str) -> dict[str, Any]:
        id_token = str(token_data.get("id_token") or "")
        if not id_token:
            raise GoogleWorkspaceError("Google did not return an OpenID identity token")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
        if response.status_code != 200:
            raise GoogleWorkspaceError("Google identity token validation failed")
        identity = response.json()
        if identity.get("aud") != self.settings.GMAIL_CLIENT_ID or identity.get("nonce") != expected_nonce:
            raise GoogleWorkspaceError("Google identity token audience or nonce did not match")
        return identity
