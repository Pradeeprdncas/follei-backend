"""Onboarding item 1 regression: industry/company_size on onboarding_profiles."""
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
    tenant = Tenant(id=tenant_id, name="Onboarding Test Co", slug=f"onboard-{tenant_id.hex[:8]}")
    db.add(tenant)
    db.commit()
    db.close()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    yield str(tenant_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM onboarding_profiles WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_profile_with_valid_industry_and_size(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "company_size": "11-50"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["industry"] == "SaaS"
    assert body["company_size"] == "11-50"


def test_create_profile_rejects_invalid_industry(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "Not A Real Industry"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_create_profile_rejects_invalid_company_size(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "company_size": "huge"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_industry_other_requires_industry_other_value_and_industry_other_field(tenant_and_token):
    _, token = tenant_and_token
    # industry_other set without industry == "Other" is rejected
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "industry_other": "Nonsense"},
        headers=_auth(token),
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "Other", "industry_other": "Space Tourism"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["industry_other"] == "Space Tourism"


def test_patch_can_update_industry(tenant_and_token):
    _, token = tenant_and_token
    client.post("/api/v1/onboarding/profile", json={"company_name": "Acme", "timezone": "Asia/Kolkata"}, headers=_auth(token))
    resp = client.patch("/api/v1/onboarding/profile", json={"industry": "Healthcare"}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["industry"] == "Healthcare"
