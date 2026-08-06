import uuid

import pytest
from fastapi.testclient import TestClient

from app.config.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.tenancy import Tenant, User
from app.services.communications.connection_verification import ProviderVerificationError, VerificationResult

client = TestClient(app)


@pytest.fixture
def tenant_user_token():
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tenant_id, name="Channel Test", slug=f"channel-{tenant_id.hex[:8]}"))
        db.flush()
        db.add(User(
            id=user_id, tenant_id=tenant_id, email=f"channel-{tenant_id.hex[:8]}@example.com",
            hashed_password="test", first_name="Channel", last_name="Tester", role="admin",
        ))
        db.commit()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id)
    yield tenant_id, user_id, token
    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant:
            db.delete(tenant)
            db.commit()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_twilio_sms_is_verified_only_after_provider_confirmation(tenant_user_token, monkeypatch):
    _, _, token = tenant_user_token

    async def confirmed(_row):
        return VerificationResult({"phone_number_sid": "PN123", "capability": "sms"})

    monkeypatch.setattr("app.routers.channel_connections.verify_channel", confirmed)
    response = client.post(
        "/api/channel-connections",
        headers=_auth(token),
        json={
            "channel": "sms", "provider": "twilio", "identity": "+15551234567",
            "account_sid": "AC123456", "auth_token": "secret-token",
            "campaign_enabled": True, "compliance_policy_version": "2026-08",
            "opt_in_acknowledged": True, "stop_help_acknowledged": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["verified"] is True
    assert body["status"] == "active"
    assert body["campaign_enabled"] is True
    assert body["compliance_ready"] is True
    assert "auth_token" not in body and "account_sid" not in body


def test_failed_provider_confirmation_never_marks_connection_verified(tenant_user_token, monkeypatch):
    _, _, token = tenant_user_token

    async def rejected(_row):
        raise ProviderVerificationError("provider rejected credentials")

    monkeypatch.setattr("app.routers.channel_connections.verify_channel", rejected)
    response = client.post(
        "/api/channel-connections",
        headers=_auth(token),
        json={
            "channel": "voice", "provider": "twilio", "identity": "+15557654321",
            "account_sid": "AC123456", "auth_token": "bad-token",
        },
    )
    assert response.status_code == 201
    assert response.json()["verified"] is False
    assert response.json()["status"] == "verification_failed"


def test_sms_campaign_cannot_be_enabled_without_compliance(tenant_user_token):
    _, _, token = tenant_user_token
    response = client.post(
        "/api/channel-connections",
        headers=_auth(token),
        json={
            "channel": "sms", "provider": "twilio", "identity": "+15550000000",
            "account_sid": "AC123456", "auth_token": "secret-token", "campaign_enabled": True,
        },
    )
    assert response.status_code == 422
