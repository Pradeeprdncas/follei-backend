"""Provider-mocked OAuth route tests; credentials must never reach UI payloads."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.routers import crm_sync, google_auth, google_workspace


class _Producer:
    def __init__(self):
        self.messages = []

    def send(self, topic, **kwargs):
        self.messages.append((topic, kwargs))

    def flush(self):
        return None


class _DB:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None

    def rollback(self):
        return None


@pytest.fixture()
def oauth_client():
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.include_router(google_workspace.router)
    api.include_router(crm_sync.router)
    api.dependency_overrides[get_db] = lambda: object()
    api.dependency_overrides[get_authenticated_tenant_id] = lambda: str(tenant_id)
    api.dependency_overrides[get_authenticated_user_id] = lambda: str(user_id)
    client = TestClient(api)
    try:
        yield client, tenant_id
    finally:
        client.close()


def test_public_google_auth_start_requests_all_workspace_resources(monkeypatch):
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: _DB()
    client = TestClient(api)
    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "create_identity_authorization_url",
        lambda *_args, **_kwargs: "https://accounts.google.test/authorize?state=opaque",
    )

    response = client.post("/api/v1/auth/google/start", json={"tenant_name": "Northstar Labs"})

    assert response.status_code == 200
    assert response.json()["data"]["resources"] == ["gmail", "drive", "calendar", "contacts"]
    assert "access_token" not in response.text.lower()
    client.close()


def test_public_google_auth_callback_uses_one_time_exchange_not_jwts(monkeypatch):
    tenant_id, user_id, connection_id, run_id = (uuid.uuid4() for _ in range(4))
    job_ids = [uuid.uuid4() for _ in range(4)]
    db = _DB()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)
    oauth_state = SimpleNamespace(
        metadata_={"resources": ["gmail", "drive", "calendar", "contacts"], "tenant_name": "Northstar Labs"}
    )
    identity = {"sub": "google-sub", "email": "maya@example.com", "email_verified": True}
    user = SimpleNamespace(id=user_id, tenant_id=tenant_id)
    connection = SimpleNamespace(id=connection_id, tenant_id=tenant_id)
    run = SimpleNamespace(id=run_id, source_id=uuid.uuid4())
    jobs = [
        SimpleNamespace(id=job_id, payload={"resource": resource})
        for job_id, resource in zip(job_ids, ["gmail", "drive", "calendar", "contacts"])
    ]
    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "complete_identity_authorization",
        AsyncMock(return_value=(oauth_state, {"access_token": "server-only"}, identity)),
    )
    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "persist_workspace_connection",
        lambda *_args, **_kwargs: (connection, run, jobs),
    )
    monkeypatch.setattr(google_auth, "_account_for_identity", lambda *_args, **_kwargs: (user, True))
    monkeypatch.setattr(google_auth, "_publish_sync_jobs", lambda *_args, **_kwargs: None)

    response = client.get("/api/v1/auth/google/callback?state=opaque&code=provider-code")

    assert response.status_code == 200
    assert "follei:auth-success" in response.text
    assert "exchange_code" in response.text
    assert "access_token" not in response.text.lower()
    assert "refresh_token" not in response.text.lower()
    assert "provider-code" not in response.text
    assert len(db.added) == 1
    client.close()


def test_public_google_auth_denial_posts_sanitized_error():
    db = _DB()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)

    response = client.get("/api/v1/auth/google/callback?error=access_denied&state=opaque")

    assert response.status_code == 200
    assert "follei:auth-error" in response.text
    assert "access_denied" not in response.text
    client.close()


def test_google_and_hubspot_oauth_start_are_frontend_safe(monkeypatch, oauth_client):
    client, _ = oauth_client
    monkeypatch.setattr(
        google_workspace.GoogleWorkspaceOAuthService,
        "create_authorization_url",
        lambda *_args, **_kwargs: "https://accounts.google.test/authorize?state=opaque",
    )
    monkeypatch.setattr(
        crm_sync.HubSpotOAuthService,
        "authorization_url",
        lambda *_args, **_kwargs: "https://hubspot.test/authorize?state=opaque",
    )

    google = client.post(
        "/api/v1/integrations/google-workspace/oauth/start",
        json={"resources": ["gmail", "drive", "calendar", "contacts"]},
    )
    hubspot = client.post("/api/v1/crm/hubspot/oauth/start")

    assert google.status_code == hubspot.status_code == 200
    for body in (google.json(), hubspot.json()):
        serialized = str(body).lower()
        assert "access_token" not in serialized
        assert "refresh_token" not in serialized
        assert "client_secret" not in serialized


def test_google_oauth_callback_uses_mocked_provider_without_exposing_tokens(monkeypatch, oauth_client):
    client, tenant_id = oauth_client
    source_id, connection_id, run_id, job_id = (uuid.uuid4() for _ in range(4))
    connection = SimpleNamespace(id=connection_id, tenant_id=tenant_id)
    run = SimpleNamespace(id=run_id, source_id=source_id)
    jobs = [SimpleNamespace(id=job_id, payload={"resource": "gmail"})]
    producer = _Producer()
    monkeypatch.setattr(
        google_workspace.GoogleWorkspaceOAuthService,
        "complete_authorization",
        AsyncMock(return_value=(connection, run, jobs)),
    )
    monkeypatch.setattr(google_workspace, "ensure_topics", lambda: None)
    monkeypatch.setattr(google_workspace, "get_producer", lambda: producer)

    response = client.get("/api/v1/integrations/google-workspace/oauth/callback?state=opaque&code=provider-code")

    assert response.status_code == 200
    assert "follei:integration-connected" in response.text
    assert str(connection_id) in response.text
    assert "access_token" not in response.text.lower()
    assert "refresh_token" not in response.text.lower()
    assert "provider-code" not in response.text
    assert producer.messages


def test_hubspot_oauth_callback_uses_mocked_provider_without_exposing_tokens(monkeypatch, oauth_client):
    client, tenant_id = oauth_client
    connection = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
    crm_run = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        crm_sync.HubSpotOAuthService,
        "complete",
        AsyncMock(return_value=connection),
    )
    monkeypatch.setattr(
        crm_sync,
        "_queue_hubspot_sync",
        lambda *_args, **_kwargs: (crm_run, SimpleNamespace(), SimpleNamespace()),
    )

    response = client.get("/api/v1/crm/hubspot/oauth/callback?state=opaque&code=provider-code")

    assert response.status_code == 200
    assert "follei:integration-connected" in response.text
    assert str(connection.id) in response.text
    assert "access_token" not in response.text.lower()
    assert "refresh_token" not in response.text.lower()
    assert "provider-code" not in response.text


@pytest.mark.parametrize(
    ("path", "service", "method"),
    [
        ("/api/v1/integrations/google-workspace/oauth/callback", google_workspace.GoogleWorkspaceOAuthService, "complete_authorization"),
        ("/api/v1/crm/hubspot/oauth/callback", crm_sync.HubSpotOAuthService, "complete"),
    ],
)
def test_oauth_callback_errors_are_sanitized(monkeypatch, oauth_client, path, service, method):
    client, _ = oauth_client
    leaked_secret = "provider-secret-that-must-not-reach-the-browser"
    monkeypatch.setattr(service, method, AsyncMock(side_effect=RuntimeError(leaked_secret)))

    response = client.get(f"{path}?state=opaque&code=provider-code")

    assert response.status_code == 200
    assert "follei:integration-error" in response.text
    assert leaked_secret not in response.text
    assert "Connection could not be completed" in response.text
