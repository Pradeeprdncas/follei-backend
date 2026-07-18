"""Onboarding item 3 regression: goals multi-select, max 3 enforced server-side."""
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
    tenant = Tenant(id=tenant_id, name="Goals Test Co", slug=f"goals-{tenant_id.hex[:8]}")
    db.add(tenant)
    db.commit()
    db.close()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    yield str(tenant_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM onboarding_goals WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM onboarding_profiles WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_with_three_goals_succeeds(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "goals": ["Increase Revenue", "Reduce Customer Churn", "Improve Conversion Rate"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert len(resp.json()["goals"]) == 3


def test_create_with_four_goals_is_rejected_with_422(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={
            "company_name": "Acme", "timezone": "Asia/Kolkata",
            "goals": ["Increase Revenue", "Reduce Customer Churn", "Improve Conversion Rate", "Track Customer Health"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert "at most 3" in resp.text


def test_invalid_goal_value_rejected(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "goals": ["Conquer The World"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_patch_adding_a_fourth_goal_is_rejected(tenant_and_token):
    _, token = tenant_and_token
    client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "goals": ["Increase Revenue", "Reduce Customer Churn"]},
        headers=_auth(token),
    )
    resp = client.patch(
        "/api/v1/onboarding/profile",
        json={"goals": ["Increase Revenue", "Reduce Customer Churn", "Improve Conversion Rate", "Track Customer Health"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_duplicate_goals_do_not_count_twice_against_the_limit(tenant_and_token):
    _, token = tenant_and_token
    resp = client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "goals": ["Increase Revenue", "Increase Revenue", "Reduce Customer Churn"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert sorted(resp.json()["goals"]) == ["Increase Revenue", "Reduce Customer Churn"]
