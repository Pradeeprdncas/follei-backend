"""Regression tests for the live POST /api/v1/auth/register endpoint:
proper typed request/response schemas (no additionalProp1 in the OpenAPI
schema), password/email validation, and a tenant_id claim on the issued JWT.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config.database import SessionLocal
from app.core.security import decode_access_token
from app.main import app

client = TestClient(app)


@pytest.fixture
def cleanup_emails():
    emails: list[str] = []
    yield emails
    if not emails:
        return
    db = SessionLocal()
    try:
        for email in emails:
            db.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        db.commit()
    finally:
        db.close()


def test_register_schema_has_no_additional_properties_allowed():
    schema = app.openapi()
    register_schema = schema["components"]["schemas"]["RegisterRequest"]
    assert register_schema.get("additionalProperties") is not True
    assert set(register_schema["required"]) == {"email", "password", "full_name", "tenant_name"}

    response_schema = schema["components"]["schemas"]["RegisterResponse"]
    assert set(response_schema["properties"].keys()) == {"user_id", "tenant_id", "access_token", "token_type", "refresh_token", "expires_in"}


def test_register_valid_payload_returns_typed_response_and_tenant_scoped_token(cleanup_emails):
    email = f"fix-register-{uuid.uuid4().hex[:10]}@example.com"
    cleanup_emails.append(email)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse1", "full_name": "Ada Lovelace", "tenant_name": "Analytical Engines Inc"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == {"user_id", "tenant_id", "access_token", "token_type", "refresh_token", "expires_in"}
    uuid.UUID(body["user_id"])
    uuid.UUID(body["tenant_id"])

    claims = decode_access_token(body["access_token"])
    assert claims["tenant_id"] == body["tenant_id"]
    assert claims["sub"] == body["user_id"]


def test_register_rejects_weak_password(cleanup_emails):
    email = f"fix-register-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "short", "full_name": "Weak Password", "tenant_name": "Weak Co"},
    )
    assert resp.status_code == 422


def test_register_rejects_password_without_a_number(cleanup_emails):
    email = f"fix-register-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "onlylettersnodigits", "full_name": "No Digits", "tenant_name": "No Digits Co"},
    )
    assert resp.status_code == 422


def test_register_rejects_malformed_email(cleanup_emails):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "correcthorse1", "full_name": "Bad Email", "tenant_name": "Bad Email Co"},
    )
    assert resp.status_code == 422


def test_register_rejects_duplicate_email(cleanup_emails):
    email = f"fix-register-{uuid.uuid4().hex[:10]}@example.com"
    cleanup_emails.append(email)
    payload = {"email": email, "password": "correcthorse1", "full_name": "Dup User", "tenant_name": "Dup Co"}
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/auth/register", json={**payload, "tenant_name": "Different Co"})
    assert second.status_code == 409
