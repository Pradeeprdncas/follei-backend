from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config.database import SessionLocal
from app.main import app
from app.models.integrations.email_connection import TenantEmailConnection
from app.services.communications.email_connections import decrypt_secret, encrypt_secret
from app.services.communications.gmail_oauth import GMAIL_SCOPES, GmailOAuthService


class _RecordingSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1


def test_authorization_url_is_tenant_bound_and_uses_pkce():
    session = _RecordingSession()
    service = GmailOAuthService()
    service.settings = SimpleNamespace(
        GMAIL_CLIENT_ID="test-client.apps.googleusercontent.com",
        GMAIL_CLIENT_SECRET="test-secret",
        GMAIL_OAUTH_REDIRECT_URI=(
            "http://127.0.0.1:8000/api/email-connections/gmail/oauth/callback"
        ),
        GMAIL_OAUTH_STATE_TTL_SECONDS=600,
    )
    tenant_id = uuid4()
    user_id = uuid4()

    authorization_url = service.create_authorization_url(
        session,
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        expected_email="owner@example.com",
        sender_name="Example Co",
        auto_reply_enabled=True,
        allow_inbound_lead_creation=True,
        campaign_enabled=True,
    )

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == set(GMAIL_SCOPES)
    assert query["login_hint"] == ["owner@example.com"]
    assert session.commits == 1
    assert len(session.added) == 1

    state_row = session.added[0]
    assert state_row.tenant_id == tenant_id
    assert state_row.user_id == user_id
    assert state_row.expected_email == "owner@example.com"
    assert state_row.state_hash != query["state"][0]
    assert decrypt_secret(state_row.encrypted_code_verifier)


def test_oauth_start_requires_an_authenticated_tenant():
    response = TestClient(app).post(
        "/api/email-connections/gmail/oauth/start",
        json={"email_address": "owner@example.com"},
    )
    assert response.status_code == 401


def test_oauth_denial_redirects_without_exposing_google_error_details():
    response = TestClient(app, follow_redirects=False).get(
        "/api/email-connections/gmail/oauth/callback",
        params={"error": "access_denied"},
    )
    assert response.status_code in {302, 307}
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert query == {
        "gmail_oauth": ["error"],
        "reason": ["authorization_denied"],
    }


def test_oauth_mailbox_can_be_paused_and_resumed_without_losing_credentials():
    client = TestClient(app)
    login_email = f"oauth-toggle-{uuid4().hex[:10]}@example.com"
    mailbox_email = f"mailbox-{uuid4().hex[:10]}@gmail.com"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": login_email,
            "password": "OAuthToggle123",
            "full_name": "OAuth Toggle",
            "tenant_name": "OAuth Toggle Tenant",
        },
    )
    assert registration.status_code == 201
    body = registration.json()
    tenant_id = UUID(body["tenant_id"])
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    with SessionLocal() as db:
        row = TenantEmailConnection(
            tenant_id=tenant_id,
            provider="gmail",
            email_address=mailbox_email,
            sender_name="Toggle Tenant",
            auth_type="oauth",
            encrypted_refresh_token=encrypt_secret("refresh-token"),
            enabled=True,
            verified=True,
            auto_reply_enabled=True,
            campaign_enabled=True,
            status="active",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        connection_id = str(row.id)

    try:
        paused = client.patch(
            f"/api/email-connections/{connection_id}",
            headers=headers,
            json={"enabled": False},
        )
        assert paused.status_code == 200
        assert paused.json()["enabled"] is False
        assert paused.json()["status"] == "paused"
        assert paused.json()["oauth_connected"] is True

        resumed = client.patch(
            f"/api/email-connections/{connection_id}",
            headers=headers,
            json={"enabled": True},
        )
        assert resumed.status_code == 200
        assert resumed.json()["enabled"] is True
        assert resumed.json()["status"] == "active"
        assert resumed.json()["oauth_connected"] is True

        renamed = client.patch(
            f"/api/email-connections/{connection_id}",
            headers=headers,
            json={"email_address": "different@gmail.com"},
        )
        assert renamed.status_code == 409
    finally:
        with SessionLocal() as db:
            db.execute(
                text("DELETE FROM tenants WHERE id = CAST(:tenant_id AS UUID)"),
                {"tenant_id": str(tenant_id)},
            )
            db.commit()
