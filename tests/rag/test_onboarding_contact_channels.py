"""Onboarding item 2 regression: contact channels are a multi-select, own table."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config.database import SessionLocal
from app.core.security import create_access_token
from app.models.tenant import Tenant
from app.main import app

client = TestClient(app)


@pytest.fixture
def tenant_and_token():
    db = SessionLocal()
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Channels Test Co", slug=f"channels-{tenant_id.hex[:8]}")
    db.add(tenant)
    db.commit()
    db.close()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    yield str(tenant_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM onboarding_contact_channels WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM onboarding_profiles WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_with_multiple_channels(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "contact_channels": ["Email", "WhatsApp"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert sorted(resp.json()["contact_channels"]) == ["Email", "WhatsApp"]
    assert resp.json()["lead_contact_requirement"] == 1


def test_invalid_channel_rejected(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "contact_channels": ["Email", "Carrier Pigeon"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_patch_replaces_channel_set(tenant_and_token):
    _, token = tenant_and_token
    client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "contact_channels": ["Email", "Phone"]},
        headers=_auth(token),
    )
    resp = client.patch("/api/v1/onboarding/profile", json={"contact_channels": ["SMS"]}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["contact_channels"] == ["SMS"]


def test_patch_without_contact_channels_leaves_existing_selection_untouched(tenant_and_token):
    _, token = tenant_and_token
    client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "contact_channels": ["Email", "Phone"]},
        headers=_auth(token),
    )
    resp = client.patch("/api/v1/onboarding/profile", json={"website": "https://acme.example"}, headers=_auth(token))
    assert resp.status_code == 200
    assert sorted(resp.json()["contact_channels"]) == ["Email", "Phone"]


def test_channel_setup_can_raise_tenant_lead_contact_requirement(tenant_and_token):
    tenant_id, token = tenant_and_token
    created = client.post(
        "/api/v1/onboarding/profile",
        json={
            "company_name": "Acme",
            "timezone": "Asia/Kolkata",
            "industry": "SaaS",
            "contact_channels": ["Email", "WhatsApp"],
            "lead_contact_requirement": 2,
        },
        headers=_auth(token),
    )
    assert created.status_code == 201
    assert created.json()["lead_contact_requirement"] == 2

    updated = client.patch(
        "/api/v1/onboarding/profile",
        json={"lead_contact_requirement": 1},
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["lead_contact_requirement"] == 1

    db = SessionLocal()
    try:
        tenant = db.get(Tenant, uuid.UUID(tenant_id))
        assert tenant.lead_contact_requirement == 1
    finally:
        db.close()


def test_duplicate_channels_are_deduplicated(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "contact_channels": ["Email", "Email", "SMS"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert sorted(resp.json()["contact_channels"]) == ["Email", "SMS"]
