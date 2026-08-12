"""One-time Google popup exchange contract against PostgreSQL."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.config.database import SessionLocal
from app.main import app
from app.models.integrations.oauth_connection import OAuthLoginExchange
from app.models.tenancy import Tenant
from app.services.integrations.oauth_security import state_hash


def test_google_exchange_issues_session_once_and_never_returns_provider_tokens():
    client = TestClient(app)
    email = f"google-exchange-{uuid4().hex[:10]}@example.com"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Temporary123",
            "full_name": "Google Exchange",
            "tenant_name": "Google Exchange Tenant",
        },
    )
    assert registration.status_code == 201
    registered = registration.json()
    tenant_id = UUID(registered["tenant_id"])
    code = "google-popup-exchange-" + uuid4().hex + uuid4().hex

    with SessionLocal() as db:
        db.add(OAuthLoginExchange(
            tenant_id=tenant_id,
            user_id=UUID(registered["user_id"]),
            provider="google",
            code_hash=state_hash(code),
            context={
                "is_new_user": False,
                "resources": ["gmail", "drive", "calendar", "contacts"],
            },
            expires_at=datetime.utcnow() + timedelta(minutes=2),
        ))
        db.commit()

    try:
        first = client.post("/api/v1/auth/google/exchange", json={"exchange_code": code})
        second = client.post("/api/v1/auth/google/exchange", json={"exchange_code": code})

        assert first.status_code == 200
        assert first.json()["status"] == "authenticated"
        assert first.json()["user"]["tenant_id"] == str(tenant_id)
        assert "access_token" in first.json()
        assert "refresh_token" in first.json()
        assert first.json()["account"] == {"is_new_user": False, "action": "signed_in"}
        assert first.json()["google_workspace"]["resources"] == ["gmail", "drive", "calendar", "contacts"]
        assert first.json()["ingestion"]["state_endpoint"] == "/api/v1/onboarding/state"
        serialized = first.text.lower()
        assert "provider_access_token" not in serialized
        assert "provider_refresh_token" not in serialized
        assert second.status_code == 401
        assert second.json() == {"detail": "Invalid or expired Google exchange code"}
    finally:
        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant_id)
            if tenant:
                db.delete(tenant)
                db.commit()
        client.close()
