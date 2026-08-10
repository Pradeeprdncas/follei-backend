"""Generalized Google Workspace OAuth and incremental resource API adapter."""
from __future__ import annotations

import base64
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
MAX_SYNC_CONTENT_BYTES = 10 * 1024 * 1024
DRIVE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "application/pdf",
    "application/vnd.google-apps.drawing": "application/pdf",
}
DRIVE_METADATA_ONLY_MIME_TYPES = {
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.site",
}


class GoogleWorkspaceError(RuntimeError):
    pass


class GoogleWorkspaceOAuthService:
    def __init__(self):
        self.settings = get_settings()

    def create_authorization_url(self, db: Session, *, tenant_id: str, user_id: str, resources: list[str]) -> str:
        return self._create_authorization_url(
            db,
            provider="google_workspace",
            redirect_uri=self.settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI,
            resources=resources,
            tenant_id=UUID(tenant_id),
            user_id=UUID(user_id),
        )

    def create_identity_authorization_url(
        self,
        db: Session,
        *,
        resources: list[str],
        tenant_name: str | None = None,
    ) -> str:
        """Start public Google identity auth plus Workspace consent."""
        return self._create_authorization_url(
            db,
            provider="google_identity_workspace",
            redirect_uri=self.settings.GOOGLE_AUTH_OAUTH_REDIRECT_URI,
            resources=resources,
            tenant_id=None,
            user_id=None,
            extra_metadata={"tenant_name": tenant_name.strip() if tenant_name else None},
        )

    def _create_authorization_url(
        self,
        db: Session,
        *,
        provider: str,
        redirect_uri: str,
        resources: list[str],
        tenant_id: UUID | None,
        user_id: UUID | None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> str:
        selected = list(dict.fromkeys(resources))
        invalid = sorted(set(selected) - set(RESOURCE_SCOPES))
        if invalid or not selected:
            raise GoogleWorkspaceError(f"Invalid Google resources: {invalid or 'none selected'}")
        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise GoogleWorkspaceError("Google OAuth client ID/secret are not configured")
        state, verifier, challenge = new_pkce()
        nonce = secrets.token_urlsafe(24)
        db.add(IntegrationOAuthState(
            tenant_id=tenant_id, user_id=user_id, provider=provider,
            state_hash=state_hash(state), encrypted_code_verifier=encrypt_secret(verifier),
            metadata_={
                "resources": selected,
                "nonce": nonce,
                "redirect_uri": redirect_uri,
                **(extra_metadata or {}),
            },
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        ))
        db.commit()
        scopes = ["openid", "email", "profile", *(RESOURCE_SCOPES[item] for item in selected)]
        query = urlencode({
            "client_id": self.settings.GMAIL_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code", "scope": " ".join(scopes), "access_type": "offline",
            "include_granted_scopes": "true", "prompt": "consent", "state": state,
            "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        })
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    async def complete_authorization(self, db: Session, *, state: str, code: str) -> tuple[GoogleWorkspaceConnection, IngestionRun, list[SourceIngestionJob]]:
        row, token_data, identity = await self._exchange_authorization(
            db,
            state=state,
            code=code,
            provider="google_workspace",
            redirect_uri=self.settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI,
        )
        if row.tenant_id is None:
            raise GoogleWorkspaceError("OAuth state is missing its tenant")
        return self.persist_workspace_connection(
            db,
            tenant_id=row.tenant_id,
            token_data=token_data,
            identity=identity,
            resources=list(row.metadata_.get("resources") or []),
        )

    async def complete_identity_authorization(
        self,
        db: Session,
        *,
        state: str,
        code: str,
    ) -> tuple[IntegrationOAuthState, dict[str, Any], dict[str, Any]]:
        """Exchange a public auth code; the router resolves/creates Follei account."""
        return await self._exchange_authorization(
            db,
            state=state,
            code=code,
            provider="google_identity_workspace",
            redirect_uri=self.settings.GOOGLE_AUTH_OAUTH_REDIRECT_URI,
        )

    async def _exchange_authorization(
        self,
        db: Session,
        *,
        state: str,
        code: str,
        provider: str,
        redirect_uri: str,
    ) -> tuple[IntegrationOAuthState, dict[str, Any], dict[str, Any]]:
        row = db.query(IntegrationOAuthState).filter(
            IntegrationOAuthState.state_hash == state_hash(state),
            IntegrationOAuthState.provider == provider,
        ).first()
        if not row or row.consumed_at or row.expires_at < datetime.utcnow():
            raise GoogleWorkspaceError("OAuth state is invalid, expired, or already used")
        row.consumed_at = datetime.utcnow()
        db.commit()
        token_data = await self._token_request({
            "client_id": self.settings.GMAIL_CLIENT_ID, "client_secret": self.settings.GMAIL_CLIENT_SECRET,
            "code": code, "code_verifier": decrypt_secret(row.encrypted_code_verifier),
            "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        })
        access_token = str(token_data.get("access_token") or "")
        identity = await self._verify_identity(token_data, expected_nonce=str(row.metadata_.get("nonce") or ""))
        subject = str(identity.get("sub") or "")
        email = str(identity.get("email") or "").strip().lower()
        if not access_token or not subject or not email or identity.get("email_verified") not in (True, "true"):
            raise GoogleWorkspaceError("Google did not return a verified Workspace identity")
        return row, token_data, identity

    def persist_workspace_connection(
        self,
        db: Session,
        *,
        tenant_id: UUID,
        token_data: dict[str, Any],
        identity: dict[str, Any],
        resources: list[str],
    ) -> tuple[GoogleWorkspaceConnection, IngestionRun, list[SourceIngestionJob]]:
        """Persist server-side provider tokens and queue one job per resource."""
        access_token = str(token_data.get("access_token") or "")
        subject = str(identity.get("sub") or "")
        email = str(identity.get("email") or "").strip().lower()
        if not access_token or not subject or not email:
            raise GoogleWorkspaceError("Google Workspace identity is incomplete")
        selected = list(dict.fromkeys(resources))
        invalid = sorted(set(selected) - set(RESOURCE_SCOPES))
        if invalid or not selected:
            raise GoogleWorkspaceError(f"Invalid Google resources: {invalid or 'none selected'}")

        connection = db.query(GoogleWorkspaceConnection).filter_by(tenant_id=tenant_id, provider_account_id=subject).first()
        source = None
        if connection and connection.source_id:
            source = db.get(KnowledgeSource, connection.source_id)
        if source is None:
            source = KnowledgeSource(
                id=uuid4(), tenant_id=tenant_id, name=f"Google Workspace: {email}",
                source_type="google_workspace", status="queued", config={"account": email, "resources": selected},
            )
            db.add(source)
        if connection is None:
            connection = GoogleWorkspaceConnection(
                tenant_id=tenant_id, provider_account_id=subject, email_address=email,
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
        connection.enabled_resources = selected
        db.flush()
        run = IngestionRun(id=uuid4(), tenant_id=tenant_id, source_id=source.id, status="queued")
        jobs = [
            SourceIngestionJob(
                id=uuid4(), tenant_id=tenant_id, run_id=run.id, job_type=f"google_{resource}_sync",
                target=email, status="queued", payload={"connection_id": str(connection.id), "resource": resource},
            )
            for resource in selected
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
        if resource not in RESOURCE_SCOPES:
            raise GoogleWorkspaceError(f"Unsupported Google resource: {resource}")
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            if resource == "gmail":
                return await self._fetch_gmail(client, headers, cursor=cursor, max_pages=max_pages)
            if resource == "drive":
                return await self._fetch_drive(client, headers, cursor=cursor, max_pages=max_pages)
            return await self._fetch_structured_resource(
                client,
                headers,
                resource=resource,
                cursor=cursor,
                max_pages=max_pages,
            )

    async def _fetch_structured_resource(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        *,
        resource: str,
        cursor: str | None,
        max_pages: int,
    ) -> tuple[list[dict], str | None]:
        records: list[dict] = []
        next_page: str | None = None
        final_cursor = cursor
        for _ in range(max_pages):
            if resource == "calendar":
                url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                params = {"maxResults": 2500, "singleEvents": "true", **({"pageToken": next_page} if next_page else {}), **({"syncToken": cursor} if cursor and not next_page else {})}
            else:
                url = "https://people.googleapis.com/v1/people/me/connections"
                params = {"pageSize": 1000, "personFields": "names,emailAddresses,phoneNumbers,organizations", "requestSyncToken": "true", **({"pageToken": next_page} if next_page else {}), **({"syncToken": cursor} if cursor and not next_page else {})}
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 410 and cursor:
                return await self.fetch_resource(headers["Authorization"].removeprefix("Bearer "), resource, cursor=None, max_pages=max_pages)
            self._require_success(response, resource)
            payload = response.json()
            records.extend(payload.get("items" if resource == "calendar" else "connections") or [])
            next_page = payload.get("nextPageToken")
            final_cursor = payload.get("nextSyncToken") or final_cursor
            if not next_page:
                break
        return records, final_cursor

    async def _fetch_gmail(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        *,
        cursor: str | None,
        max_pages: int,
    ) -> tuple[list[dict], str | None]:
        message_ids: list[str] = []
        next_page: str | None = None
        final_cursor = cursor
        for _ in range(max_pages):
            if cursor:
                url = "https://gmail.googleapis.com/gmail/v1/users/me/history"
                params = {
                    "startHistoryId": cursor,
                    "historyTypes": "messageAdded",
                    "maxResults": 100,
                    **({"pageToken": next_page} if next_page else {}),
                }
            else:
                url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
                params = {"maxResults": 100, **({"pageToken": next_page} if next_page else {})}
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 404 and cursor:
                return await self._fetch_gmail(client, headers, cursor=None, max_pages=max_pages)
            if response.status_code == 410 and cursor:
                return await self._fetch_gmail(client, headers, cursor=None, max_pages=max_pages)
            self._require_success(response, "gmail")
            payload = response.json()
            if cursor:
                final_cursor = str(payload.get("historyId") or final_cursor or "") or None
                for history in payload.get("history") or []:
                    for added in history.get("messagesAdded") or []:
                        message_id = str((added.get("message") or {}).get("id") or "")
                        if message_id:
                            message_ids.append(message_id)
            else:
                message_ids.extend(str(item.get("id")) for item in payload.get("messages") or [] if item.get("id"))
            next_page = payload.get("nextPageToken")
            if not next_page:
                break

        records = []
        for message_id in dict.fromkeys(message_ids):
            records.append(await self._fetch_gmail_message(client, headers, message_id))

        profile = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers=headers,
        )
        if profile.status_code == 200:
            final_cursor = str(profile.json().get("historyId") or final_cursor or "") or None
        return records, final_cursor

    async def _fetch_gmail_message(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        message_id: str,
    ) -> dict[str, Any]:
        response = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            params={"format": "full"},
            headers=headers,
        )
        self._require_success(response, "gmail")
        message = response.json()
        body_text: list[str] = []
        body_html: list[str] = []
        attachments: list[dict[str, Any]] = []
        await self._read_gmail_part(
            client,
            headers,
            message_id=message_id,
            part=message.get("payload") or {},
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
        )
        header_values = {
            str(item.get("name") or "").lower(): str(item.get("value") or "")
            for item in (message.get("payload") or {}).get("headers") or []
            if item.get("name")
        }
        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds") or [],
            "snippet": message.get("snippet"),
            "internal_date": message.get("internalDate"),
            "headers": header_values,
            "body_text": "\n".join(value for value in body_text if value).strip(),
            "body_html": "\n".join(value for value in body_html if value).strip(),
            "attachments": attachments,
        }

    async def _read_gmail_part(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        *,
        message_id: str,
        part: dict[str, Any],
        body_text: list[str],
        body_html: list[str],
        attachments: list[dict[str, Any]],
    ) -> None:
        filename = str(part.get("filename") or "")
        mime_type = str(part.get("mimeType") or "application/octet-stream")
        body = part.get("body") or {}
        encoded = str(body.get("data") or "")
        attachment_id = str(body.get("attachmentId") or "")
        if attachment_id:
            response = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
                headers=headers,
            )
            self._require_success(response, "gmail attachment")
            encoded = str(response.json().get("data") or "")
        content = self._decode_websafe(encoded) if encoded else b""
        if filename or attachment_id:
            attachments.append({
                "attachment_id": attachment_id or None,
                "filename": filename or f"attachment-{len(attachments) + 1}",
                "mime_type": mime_type,
                **self._serialize_content(content, mime_type),
            })
        elif content and mime_type == "text/plain":
            body_text.append(content.decode("utf-8", errors="replace"))
        elif content and mime_type == "text/html":
            body_html.append(content.decode("utf-8", errors="replace"))
        for child in part.get("parts") or []:
            await self._read_gmail_part(
                client,
                headers,
                message_id=message_id,
                part=child,
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
            )

    async def _fetch_drive(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        *,
        cursor: str | None,
        max_pages: int,
    ) -> tuple[list[dict], str | None]:
        files: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        next_page = cursor if cursor else None
        final_cursor = cursor
        for _ in range(max_pages):
            if cursor:
                response = await client.get(
                    "https://www.googleapis.com/drive/v3/changes",
                    params={
                        "pageToken": next_page,
                        "pageSize": 100,
                        "includeRemoved": "true",
                        "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,webViewLink,description,size,md5Checksum))",
                    },
                    headers=headers,
                )
            else:
                response = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    params={
                        "pageSize": 100,
                        "q": "trashed = false",
                        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,description,size,md5Checksum)",
                        **({"pageToken": next_page} if next_page else {}),
                    },
                    headers=headers,
                )
            if response.status_code == 410 and cursor:
                return await self._fetch_drive(client, headers, cursor=None, max_pages=max_pages)
            self._require_success(response, "drive")
            payload = response.json()
            if cursor:
                for change in payload.get("changes") or []:
                    if change.get("removed"):
                        removed.append({"id": change.get("fileId"), "removed": True})
                    elif change.get("file"):
                        files.append(change["file"])
                final_cursor = payload.get("newStartPageToken") or final_cursor
            else:
                files.extend(payload.get("files") or [])
            next_page = payload.get("nextPageToken")
            if not next_page:
                break

        records = [await self._fetch_drive_file_content(client, headers, file) for file in files]
        records.extend(removed)
        if not cursor:
            start = await client.get(
                "https://www.googleapis.com/drive/v3/changes/startPageToken",
                headers=headers,
            )
            if start.status_code == 200:
                final_cursor = start.json().get("startPageToken")
        return records, final_cursor

    async def _fetch_drive_file_content(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        file: dict[str, Any],
    ) -> dict[str, Any]:
        record = dict(file)
        file_id = str(file.get("id") or "")
        mime_type = str(file.get("mimeType") or "application/octet-stream")
        if not file_id or mime_type in DRIVE_METADATA_ONLY_MIME_TYPES:
            record["content_status"] = "metadata_only"
            return record
        export_type = DRIVE_EXPORT_MIME_TYPES.get(mime_type)
        if mime_type.startswith("application/vnd.google-apps.") and not export_type:
            record["content_status"] = "unsupported_google_type"
            return record
        if export_type:
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
            params = {"mimeType": export_type}
            content_type = export_type
        else:
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            params = {"alt": "media"}
            content_type = mime_type
        response = await client.get(url, params=params, headers=headers)
        if response.status_code in {403, 404}:
            record.update({"content_status": "unavailable", "content_error_status": response.status_code})
            return record
        self._require_success(response, "drive content")
        if len(response.content) > MAX_SYNC_CONTENT_BYTES:
            record.update({
                "content_status": "skipped_too_large",
                "content_size": len(response.content),
                "content_limit": MAX_SYNC_CONTENT_BYTES,
            })
            return record
        record.update({"content_status": "synced", "content_mime_type": content_type})
        record.update(self._serialize_content(response.content, content_type))
        return record

    @staticmethod
    def _require_success(response: httpx.Response, resource: str) -> None:
        if response.status_code >= 400:
            raise GoogleWorkspaceError(f"Google {resource} sync failed ({response.status_code})")

    @staticmethod
    def _decode_websafe(value: str) -> bytes:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    @staticmethod
    def _serialize_content(content: bytes, mime_type: str) -> dict[str, Any]:
        result: dict[str, Any] = {"content_size": len(content)}
        textual = mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/xml",
            "application/csv",
        }
        if textual:
            result.update({"content_text": content.decode("utf-8", errors="replace"), "content_encoding": "utf-8"})
        else:
            result.update({"content_base64": base64.b64encode(content).decode("ascii"), "content_encoding": "base64"})
        return result

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
