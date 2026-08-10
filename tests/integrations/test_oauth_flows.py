"""Provider-mocked OAuth route tests; credentials must never reach UI payloads."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
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
    assert "https://www.googleapis.com/auth/gmail.modify" in response.json()["data"]["scopes"]
    assert "https://www.googleapis.com/auth/gmail.send" in response.json()["data"]["scopes"]
    assert response.json()["data"]["gmail_communication"] == {
        "requested": True,
        "capabilities": ["send", "reply", "read_inbound"],
    }
    assert "access_token" not in response.text.lower()
    client.close()


def test_public_google_auth_start_accepts_a_truly_empty_request(monkeypatch):
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: _DB()
    client = TestClient(api)
    captured = {}

    def _authorization_url(*_args, **kwargs):
        captured.update(kwargs)
        return "https://accounts.google.test/authorize?state=opaque"

    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "create_identity_authorization_url",
        _authorization_url,
    )

    response = client.post("/api/v1/auth/google/start")

    assert response.status_code == 200
    assert captured["tenant_name"] is None
    assert response.json()["data"]["authorization_url"].startswith("https://accounts.google.test/")
    client.close()


def test_public_google_auth_start_treats_blank_tenant_name_as_omitted(monkeypatch):
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: _DB()
    client = TestClient(api)
    captured = {}

    def _authorization_url(*_args, **kwargs):
        captured.update(kwargs)
        return "https://accounts.google.test/authorize?state=opaque"

    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "create_identity_authorization_url",
        _authorization_url,
    )

    response = client.post("/api/v1/auth/google/start", json={"tenant_name": ""})

    assert response.status_code == 200
    assert captured["tenant_name"] is None
    assert response.json()["data"]["flow"] == "account_auth"
    assert response.json()["data"]["requires_bearer"] is False
    client.close()


def test_public_google_auth_callback_redirects_one_time_exchange_not_jwts(monkeypatch):
    tenant_id, user_id, connection_id, email_connection_id, run_id = (uuid.uuid4() for _ in range(5))
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
    email_connection = SimpleNamespace(id=email_connection_id)
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
    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "persist_gmail_communication_connection",
        lambda *_args, **_kwargs: email_connection,
    )
    monkeypatch.setattr(google_auth, "_account_for_identity", lambda *_args, **_kwargs: (user, True))
    monkeypatch.setattr(google_auth, "_publish_sync_jobs", lambda *_args, **_kwargs: None)

    response = client.get(
        "/api/v1/auth/google/callback?state=opaque&code=provider-code",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert location.path == "/auth/callback"
    assert set(query) == {
        "exchange_code",
        "expires_in",
        "is_new_user",
        "connection_id",
        "email_connection_id",
        "gmail_communication",
        "run_id",
        "resources",
    }
    assert query["expires_in"] == ["120"]
    assert query["is_new_user"] == ["true"]
    assert query["connection_id"] == [str(connection_id)]
    assert query["email_connection_id"] == [str(email_connection_id)]
    assert query["gmail_communication"] == ["connected"]
    assert query["run_id"] == [str(run_id)]
    assert query["resources"] == ["gmail,drive,calendar,contacts"]
    assert "access_token" not in response.headers["location"].lower()
    assert "refresh_token" not in response.headers["location"].lower()
    assert "provider-code" not in response.headers["location"]
    assert len(db.added) == 1
    assert db.added[0].context == {
        "is_new_user": True,
        "workspace_connection_id": str(connection_id),
        "email_connection_id": str(email_connection_id),
        "run_id": str(run_id),
        "resources": ["gmail", "drive", "calendar", "contacts"],
    }
    client.close()


def test_public_google_auth_callback_does_not_fail_when_sync_dispatch_is_offline(monkeypatch):
    tenant_id, user_id, connection_id, email_connection_id, run_id = (uuid.uuid4() for _ in range(5))
    db = _DB()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)
    oauth_state = SimpleNamespace(metadata_={"resources": ["gmail"], "tenant_name": None})
    identity = {"sub": "google-sub", "email": "maya@example.com", "email_verified": True}
    user = SimpleNamespace(id=user_id, tenant_id=tenant_id)
    connection = SimpleNamespace(id=connection_id, tenant_id=tenant_id)
    email_connection = SimpleNamespace(id=email_connection_id)
    run = SimpleNamespace(id=run_id, source_id=uuid.uuid4())
    jobs = [SimpleNamespace(id=uuid.uuid4(), payload={"resource": "gmail"})]
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
    monkeypatch.setattr(
        google_auth.GoogleWorkspaceOAuthService,
        "persist_gmail_communication_connection",
        lambda *_args, **_kwargs: email_connection,
    )
    monkeypatch.setattr(google_auth, "_account_for_identity", lambda *_args, **_kwargs: (user, True))
    monkeypatch.setattr(
        google_auth,
        "_publish_sync_jobs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("broker offline")),
    )

    response = client.get(
        "/api/v1/auth/google/callback?state=opaque&code=provider-code",
        follow_redirects=False,
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert "exchange_code" in query
    assert "error" not in query
    client.close()


def test_public_google_auth_denial_redirects_with_sanitized_error():
    db = _DB()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)

    response = client.get(
        "/api/v1/auth/google/callback",
        params={
            "error": "access_denied",
            "state": "opaque",
            "error_description": "provider-secret-that-must-not-reach-frontend",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.path == "/auth/callback"
    assert parse_qs(location.query) == {"error": ["access_denied"]}
    assert "provider-secret" not in response.headers["location"]
    client.close()


def test_public_google_auth_invalid_callback_redirects_generic_safe_error():
    db = _DB()
    api = FastAPI()
    api.include_router(google_auth.router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)

    response = client.get(
        "/api/v1/auth/google/callback?state=opaque-without-code",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.path == "/auth/callback"
    assert parse_qs(location.query) == {"error": ["oauth_failed"]}
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
