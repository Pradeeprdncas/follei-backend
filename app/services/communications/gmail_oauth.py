"""Tenant-scoped Gmail OAuth and Gmail REST API operations."""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.integrations.email_connection import EmailOAuthState, TenantEmailConnection
from app.services.communications.email_connections import decrypt_secret, encrypt_secret

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailOAuthError(RuntimeError):
    pass


def _urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_header(value: str | None) -> str:
    return " ".join((value or "").split())


class GmailOAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _require_configuration(self) -> None:
        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise GmailOAuthError("Gmail OAuth client ID/secret are not configured")
        if not self.settings.GMAIL_OAUTH_REDIRECT_URI:
            raise GmailOAuthError("GMAIL_OAUTH_REDIRECT_URI is not configured")

    def create_authorization_url(
        self,
        db: Session,
        *,
        tenant_id: str,
        user_id: str,
        expected_email: str | None,
        sender_name: str,
        auto_reply_enabled: bool,
        allow_inbound_lead_creation: bool,
        campaign_enabled: bool,
    ) -> str:
        self._require_configuration()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = _urlsafe(hashlib.sha256(code_verifier.encode("ascii")).digest())
        ttl = max(120, min(int(self.settings.GMAIL_OAUTH_STATE_TTL_SECONDS), 1800))
        db.add(EmailOAuthState(
            tenant_id=UUID(tenant_id),
            user_id=UUID(user_id),
            provider="gmail",
            state_hash=_state_hash(state),
            encrypted_code_verifier=encrypt_secret(code_verifier),
            expected_email=(expected_email or "").strip().lower() or None,
            sender_name=sender_name.strip() or "Follei",
            auto_reply_enabled=auto_reply_enabled,
            allow_inbound_lead_creation=allow_inbound_lead_creation,
            campaign_enabled=campaign_enabled,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        ))
        db.commit()
        query = urlencode({
            "client_id": self.settings.GMAIL_CLIENT_ID,
            "redirect_uri": self.settings.GMAIL_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            **({"login_hint": expected_email} if expected_email else {}),
        })
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    async def complete_authorization(self, db: Session, *, state: str, code: str) -> TenantEmailConnection:
        self._require_configuration()
        state_row = db.query(EmailOAuthState).filter(
            EmailOAuthState.state_hash == _state_hash(state),
            EmailOAuthState.provider == "gmail",
        ).first()
        if not state_row or state_row.consumed_at is not None:
            raise GmailOAuthError("OAuth state is invalid or already used")
        if state_row.expires_at < datetime.utcnow():
            raise GmailOAuthError("OAuth state expired; start Gmail connection again")
        state_row.consumed_at = datetime.utcnow()
        db.commit()

        token_data = await self._token_request({
            "client_id": self.settings.GMAIL_CLIENT_ID,
            "client_secret": self.settings.GMAIL_CLIENT_SECRET,
            "code": code,
            "code_verifier": decrypt_secret(state_row.encrypted_code_verifier),
            "grant_type": "authorization_code",
            "redirect_uri": self.settings.GMAIL_OAUTH_REDIRECT_URI,
        })
        access_token = str(token_data.get("access_token") or "")
        if not access_token:
            raise GmailOAuthError("Google did not return an access token")
        profile = await self._request("GET", "/profile", access_token=access_token)
        email_address = str(profile.get("emailAddress") or "").strip().lower()
        if not email_address:
            raise GmailOAuthError("Google did not return the Gmail account address")
        if state_row.expected_email and email_address != state_row.expected_email:
            raise GmailOAuthError(
                f"Connected Gmail address does not match the requested business inbox ({state_row.expected_email})"
            )

        conflicting = db.query(TenantEmailConnection).filter(
            TenantEmailConnection.provider == "gmail",
            TenantEmailConnection.email_address == email_address,
            TenantEmailConnection.enabled.is_(True),
            TenantEmailConnection.tenant_id != state_row.tenant_id,
        ).first()
        if conflicting:
            raise GmailOAuthError("This Gmail inbox is already connected to another Follei tenant")

        row = db.query(TenantEmailConnection).filter(
            TenantEmailConnection.tenant_id == state_row.tenant_id,
            TenantEmailConnection.provider == "gmail",
            TenantEmailConnection.email_address == email_address,
        ).first()
        if row is None and state_row.expected_email:
            row = db.query(TenantEmailConnection).filter(
                TenantEmailConnection.tenant_id == state_row.tenant_id,
                TenantEmailConnection.provider == "gmail",
                TenantEmailConnection.email_address == state_row.expected_email,
                TenantEmailConnection.status == "oauth_required",
            ).first()
        if row is None:
            row = TenantEmailConnection(
                tenant_id=state_row.tenant_id,
                provider="gmail",
                email_address=email_address,
            )
            db.add(row)

        refresh_token = str(token_data.get("refresh_token") or "")
        if not refresh_token and not row.encrypted_refresh_token:
            raise GmailOAuthError("Google did not return a refresh token; revoke Follei access and reconnect")
        row.email_address = email_address
        row.sender_name = state_row.sender_name or "Follei"
        row.auth_type = "oauth"
        row.encrypted_access_token = encrypt_secret(access_token)
        if refresh_token:
            row.encrypted_refresh_token = encrypt_secret(refresh_token)
        row.access_token_expires_at = datetime.utcnow() + timedelta(
            seconds=max(60, int(token_data.get("expires_in") or 3600))
        )
        row.oauth_scopes = str(token_data.get("scope") or " ".join(GMAIL_SCOPES)).split()
        row.provider_account_id = email_address
        row.gmail_history_id = str(profile.get("historyId") or "") or None
        row.token_updated_at = datetime.utcnow()
        row.enabled = True
        row.verified = True
        row.auto_reply_enabled = bool(state_row.auto_reply_enabled)
        row.allow_inbound_lead_creation = bool(state_row.allow_inbound_lead_creation)
        row.campaign_enabled = bool(state_row.campaign_enabled)
        row.status = "active"
        row.last_error = None
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise GmailOAuthError(
                "This Gmail inbox became connected to another Follei tenant; reconnect with a different inbox"
            ) from exc
        db.refresh(row)
        return row

    async def valid_access_token(self, db: Session, row: TenantEmailConnection) -> str:
        if row.auth_type != "oauth" or not row.encrypted_refresh_token:
            raise GmailOAuthError("Gmail OAuth connection is incomplete")
        if (
            row.encrypted_access_token
            and row.access_token_expires_at
            and row.access_token_expires_at > datetime.utcnow() + timedelta(seconds=60)
        ):
            return decrypt_secret(row.encrypted_access_token)
        token_data = await self._token_request({
            "client_id": self.settings.GMAIL_CLIENT_ID,
            "client_secret": self.settings.GMAIL_CLIENT_SECRET,
            "refresh_token": decrypt_secret(row.encrypted_refresh_token),
            "grant_type": "refresh_token",
        })
        access_token = str(token_data.get("access_token") or "")
        if not access_token:
            raise GmailOAuthError("Google token refresh returned no access token")
        row.encrypted_access_token = encrypt_secret(access_token)
        row.access_token_expires_at = datetime.utcnow() + timedelta(
            seconds=max(60, int(token_data.get("expires_in") or 3600))
        )
        row.token_updated_at = datetime.utcnow()
        row.status = "active"
        row.verified = True
        row.last_error = None
        db.commit()
        return access_token

    async def send_for_tenant(
        self,
        *,
        tenant_id: str,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        thread_id: str | None = None,
        require_campaign_enabled: bool = False,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            query = db.query(TenantEmailConnection).filter(
                TenantEmailConnection.tenant_id == UUID(tenant_id),
                TenantEmailConnection.provider == "gmail",
                TenantEmailConnection.auth_type == "oauth",
                TenantEmailConnection.enabled.is_(True),
                TenantEmailConnection.verified.is_(True),
                TenantEmailConnection.status == "active",
            )
            if require_campaign_enabled:
                query = query.filter(TenantEmailConnection.campaign_enabled.is_(True))
            row = query.order_by(TenantEmailConnection.updated_at.desc()).first()
            if not row:
                raise GmailOAuthError("No active tenant Gmail OAuth connection is available")
            access_token = await self.valid_access_token(db, row)
            sender_email = row.email_address
            sender_name = row.sender_name or "Follei"

        message = EmailMessage()
        message["From"] = f"{sender_name} <{sender_email}>"
        message["To"] = to_email
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=sender_email.split("@", 1)[-1])
        safe_in_reply_to = _safe_header(in_reply_to)
        if safe_in_reply_to:
            message["In-Reply-To"] = safe_in_reply_to
            message["References"] = " ".join(filter(None, [_safe_header(references), safe_in_reply_to]))
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        for item in attachments or []:
            content_type = str(item.get("content_type") or "application/octet-stream")
            main_type, sub_type = (content_type.split("/", 1) + ["octet-stream"])[:2]
            message.add_attachment(
                item.get("content_bytes") or b"",
                maintype=main_type,
                subtype=sub_type,
                filename=str(item.get("name") or "attachment"),
            )
        payload: dict[str, Any] = {"raw": _urlsafe(message.as_bytes())}
        if thread_id:
            payload["threadId"] = thread_id
        data = await self._request("POST", "/messages/send", access_token=access_token, json=payload)
        return {
            "success": True,
            "message_id": data.get("id") or str(message["Message-ID"]),
            "thread_id": data.get("threadId"),
            "status": "sent",
            "provider": "gmail",
        }

    async def fetch_history(self, connection_id: str, max_messages: int = 25) -> dict[str, Any]:
        with SessionLocal() as db:
            row = db.get(TenantEmailConnection, UUID(connection_id))
            if not row or row.auth_type != "oauth":
                return {"entries": [], "history_id": None}
            access_token = await self.valid_access_token(db, row)
            start_history_id = row.gmail_history_id
            if not start_history_id:
                profile = await self._request("GET", "/profile", access_token=access_token)
                row.gmail_history_id = str(profile.get("historyId") or "") or None
                db.commit()
                return {"entries": [], "history_id": row.gmail_history_id}

        response = await self._request(
            "GET",
            "/history",
            access_token=access_token,
            params={
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "maxResults": min(max_messages * 4, 100),
            },
            allow_history_reset=True,
        )
        if response.get("_history_expired"):
            with SessionLocal() as db:
                row = db.get(TenantEmailConnection, UUID(connection_id))
                token = await self.valid_access_token(db, row)
                profile = await self._request("GET", "/profile", access_token=token)
                row.gmail_history_id = str(profile.get("historyId") or "") or None
                row.last_error = None
                db.commit()
                return {"entries": [], "history_id": row.gmail_history_id}

        seen: set[str] = set()
        message_refs: list[dict[str, str]] = []
        for history in response.get("history") or []:
            for added in history.get("messagesAdded") or []:
                message = added.get("message") or {}
                message_id = str(message.get("id") or "")
                if message_id and message_id not in seen:
                    seen.add(message_id)
                    message_refs.append({"id": message_id, "thread_id": str(message.get("threadId") or "")})
        entries = []
        for item in message_refs[:max_messages]:
            data = await self._request(
                "GET",
                f"/messages/{item['id']}",
                access_token=access_token,
                params={"format": "raw"},
            )
            labels = set(data.get("labelIds") or [])
            if "UNREAD" not in labels:
                continue
            raw = str(data.get("raw") or "")
            if not raw:
                continue
            raw += "=" * (-len(raw) % 4)
            entries.append({
                "api_message_id": item["id"],
                "thread_id": str(data.get("threadId") or item["thread_id"]),
                "raw_bytes": base64.urlsafe_b64decode(raw),
            })
        return {
            "entries": entries,
            "history_id": str(response.get("historyId") or start_history_id),
        }

    async def mark_read(self, connection_id: str, api_message_id: str) -> None:
        with SessionLocal() as db:
            row = db.get(TenantEmailConnection, UUID(connection_id))
            if not row or row.auth_type != "oauth":
                raise GmailOAuthError("Gmail OAuth connection is unavailable")
            access_token = await self.valid_access_token(db, row)
        await self._request(
            "POST",
            f"/messages/{api_message_id}/modify",
            access_token=access_token,
            json={"removeLabelIds": ["UNREAD"]},
        )

    async def revoke_connection(self, db: Session, row: TenantEmailConnection) -> None:
        token = decrypt_secret(row.encrypted_refresh_token) if row.encrypted_refresh_token else ""
        if token:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": token},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
            except httpx.HTTPError:
                # Local disconnect must still remove usable credentials if Google
                # is temporarily unreachable. Google tokens can also be revoked
                # later from the account's third-party access settings.
                pass
        row.encrypted_access_token = None
        row.encrypted_refresh_token = None
        row.access_token_expires_at = None
        row.verified = False
        row.enabled = False
        row.status = "disconnected"
        row.last_error = None
        db.commit()

    @staticmethod
    def store_history_id(connection_id: str, history_id: str | None) -> None:
        if not history_id:
            return
        with SessionLocal() as db:
            row = db.get(TenantEmailConnection, UUID(connection_id))
            if row:
                row.gmail_history_id = str(history_id)
                db.commit()

    async def _token_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=payload)
        if response.status_code != 200:
            raise GmailOAuthError(f"Google token request failed ({response.status_code})")
        return response.json()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        allow_history_reset: bool = False,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{GMAIL_API_BASE}{path}",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                params=params,
                json=json,
            )
        if allow_history_reset and response.status_code == 404:
            return {"_history_expired": True}
        if response.status_code < 200 or response.status_code >= 300:
            raise GmailOAuthError(f"Gmail API request failed ({response.status_code})")
        return response.json() if response.content else {}
