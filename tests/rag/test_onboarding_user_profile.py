"""Onboarding item 4 regression: user profile fields on the existing users table."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config.database import SessionLocal
from app.core.security import create_access_token, hash_password
from app.main import app

client = TestClient(app)


@pytest.fixture
def user_and_token():
    db = SessionLocal()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = f"item4-{uuid.uuid4().hex[:10]}@example.com"
    db.execute(
        text("INSERT INTO tenants (id, name, slug, status, is_active, timezone, auto_reply_enabled, created_at, updated_at) VALUES (:id, :name, :slug, 'active', true, 'Asia/Kolkata', false, now(), now())"),
        {"id": tenant_id, "name": "Item4 Co", "slug": f"item4-{tenant_id.hex[:8]}"},
    )
    db.execute(
        text("""INSERT INTO users (id, tenant_id, email, hashed_password, first_name, last_name, full_name, role, status, is_active, created_at, updated_at)
                VALUES (:id, :tenant_id, :email, :hp, 'Test', 'User', 'Test User', 'admin', 'active', true, now(), now())"""),
        {"id": user_id, "tenant_id": tenant_id, "email": email, "hp": hash_password("irrelevant1")},
    )
    db.commit()
    db.close()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id)
    yield str(tenant_id), str(user_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(user_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_update_mobile_and_job_title(user_and_token):
    _, _, token = user_and_token
    resp = client.patch(
        "/api/v1/onboarding/user-profile",
        json={"mobile_number": "+919876543210", "job_title": "Founder"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mobile_number"] == "+919876543210"
    assert body["job_title"] == "Founder"
    assert body["terms_accepted"] is False


def test_terms_accepted_true_is_recorded(user_and_token):
    _, _, token = user_and_token
    resp = client.patch("/api/v1/onboarding/user-profile", json={"terms_accepted": True}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["terms_accepted"] is True


def test_terms_accepted_omitted_does_not_reset_prior_acceptance(user_and_token):
    _, _, token = user_and_token
    client.patch("/api/v1/onboarding/user-profile", json={"terms_accepted": True}, headers=_auth(token))
    resp = client.patch("/api/v1/onboarding/user-profile", json={"job_title": "CEO"}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["terms_accepted"] is True
    assert resp.json()["job_title"] == "CEO"


def test_email_field_is_not_accepted_in_payload(user_and_token):
    _, _, token = user_and_token
    resp = client.patch("/api/v1/onboarding/user-profile", json={"email": "new@example.com"}, headers=_auth(token))
    # extra field is silently ignored (no email-change mutation path exists here)
    assert resp.status_code == 200
    assert resp.json()["email"] != "new@example.com"
