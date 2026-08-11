"""Execution-backed passwordless authentication and anti-enumeration tests."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.config.database import SessionLocal
from app.main import app
from app.models.auth_otp import AuthOtpChallenge
from app.models.tenancy import Tenant
from app.routers import api_v1


def _register(client: TestClient) -> tuple[str, UUID]:
    email = f"passwordless-{uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Temporary123",
            "full_name": "Passwordless User",
            "tenant_name": f"Passwordless {uuid4().hex[:10]}",
        },
    )
    assert response.status_code == 201
    return email, UUID(response.json()["tenant_id"])


def _cleanup_tenant(tenant_id: UUID) -> None:
    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant:
            db.delete(tenant)
            db.commit()


def test_valid_otp_flow_returns_login_session(monkeypatch):
    delivered: dict[str, str] = {}

    async def capture(email: str, code: str) -> None:
        delivered[email] = code

    monkeypatch.setattr(api_v1, "_deliver_login_otp", capture)
    with TestClient(app) as client:
        email, tenant_id = _register(client)
        try:
            requested = client.post("/api/v1/auth/otp/request", json={"email": email})
            assert requested.status_code == 200
            assert requested.json() == {
                "message": "If an account exists, a sign-in code has been sent.",
                "expires_in": api_v1._settings.AUTH_OTP_TTL_SECONDS,
            }
            verified = client.post(
                "/api/v1/auth/otp/verify",
                json={"email": email, "code": delivered[email]},
            )
            assert verified.status_code == 200
            body = verified.json()
            assert body["token_type"] == "bearer"
            assert body["access_token"]
            assert body["refresh_token"]
            assert body["user"]["email"] == email
            assert body["user"]["tenant_id"] == str(tenant_id)
        finally:
            _cleanup_tenant(tenant_id)


def test_expired_otp_is_rejected(monkeypatch):
    delivered: dict[str, str] = {}

    async def capture(email: str, code: str) -> None:
        delivered[email] = code

    monkeypatch.setattr(api_v1, "_deliver_login_otp", capture)
    with TestClient(app) as client:
        email, tenant_id = _register(client)
        try:
            client.post("/api/v1/auth/otp/request", json={"email": email})
            with SessionLocal() as db:
                challenge = db.query(AuthOtpChallenge).filter(
                    AuthOtpChallenge.email_hash == api_v1._email_hash(email)
                ).order_by(AuthOtpChallenge.created_at.desc()).first()
                challenge.expires_at = datetime.utcnow() - timedelta(seconds=1)
                db.commit()
            response = client.post(
                "/api/v1/auth/otp/verify",
                json={"email": email, "code": delivered[email]},
            )
            assert response.status_code == 401
            assert response.json() == {"detail": "Invalid or expired sign-in code"}
        finally:
            _cleanup_tenant(tenant_id)


def test_consumed_otp_cannot_be_reused(monkeypatch):
    delivered: dict[str, str] = {}

    async def capture(email: str, code: str) -> None:
        delivered[email] = code

    monkeypatch.setattr(api_v1, "_deliver_login_otp", capture)
    with TestClient(app) as client:
        email, tenant_id = _register(client)
        try:
            client.post("/api/v1/auth/otp/request", json={"email": email})
            payload = {"email": email, "code": delivered[email]}
            assert client.post("/api/v1/auth/otp/verify", json=payload).status_code == 200
            reused = client.post("/api/v1/auth/otp/verify", json=payload)
            assert reused.status_code == 401
            assert reused.json() == {"detail": "Invalid or expired sign-in code"}
        finally:
            _cleanup_tenant(tenant_id)


def test_nonexistent_email_request_has_same_generic_success(monkeypatch):
    delivered: list[tuple[str, str]] = []

    async def capture(email: str, code: str) -> None:
        delivered.append((email, code))

    monkeypatch.setattr(api_v1, "_deliver_login_otp", capture)
    email = f"does-not-exist-{uuid4().hex}@example.com"
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/otp/request", json={"email": email})
    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists, a sign-in code has been sent.",
        "expires_in": api_v1._settings.AUTH_OTP_TTL_SECONDS,
    }
    assert delivered == []
    with SessionLocal() as db:
        db.query(AuthOtpChallenge).filter(
            AuthOtpChallenge.email_hash == api_v1._email_hash(email)
        ).delete(synchronize_session=False)
        db.commit()


def test_otp_request_and_verify_are_rate_limited_per_email(monkeypatch):
    delivered: dict[str, str] = {}

    async def capture(email: str, code: str) -> None:
        delivered[email] = code

    monkeypatch.setattr(api_v1, "_deliver_login_otp", capture)
    with TestClient(app) as client:
        email, tenant_id = _register(client)
        try:
            bodies = [
                client.post("/api/v1/auth/otp/request", json={"email": email}).json()
                for _ in range(api_v1._settings.AUTH_OTP_REQUEST_LIMIT + 1)
            ]
            assert all(body == bodies[0] for body in bodies)
            with SessionLocal() as db:
                count = db.query(AuthOtpChallenge).filter(
                    AuthOtpChallenge.email_hash == api_v1._email_hash(email)
                ).count()
            assert count == api_v1._settings.AUTH_OTP_REQUEST_LIMIT

            invalid_code = "000000" if delivered[email] != "000000" else "999999"
            for _ in range(api_v1._settings.AUTH_OTP_VERIFY_LIMIT):
                rejected = client.post(
                    "/api/v1/auth/otp/verify",
                    json={"email": email, "code": invalid_code},
                )
                assert rejected.status_code == 401
            limited = client.post(
                "/api/v1/auth/otp/verify",
                json={"email": email, "code": delivered[email]},
            )
            assert limited.status_code == 429
        finally:
            _cleanup_tenant(tenant_id)
