import uuid

from fastapi.testclient import TestClient

from app.config.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.integrations.email_connection import TenantEmailConnection
from app.models.tenancy import Tenant
from app.services.communications.connection_verification import VerificationResult
from app.services.communications.email_connections import encrypt_secret

client = TestClient(app)


def test_brevo_sender_becomes_active_only_after_live_verification(monkeypatch):
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tenant_id, name="Mail Verify", slug=f"mail-{tenant_id.hex[:8]}"))
        db.flush()
        row = TenantEmailConnection(
            tenant_id=tenant_id, provider="brevo", email_address=f"sender-{tenant_id.hex[:8]}@example.com",
            sender_name="Mail Verify", auth_type="api_key", encrypted_api_key=encrypt_secret("test-api-key"),
            enabled=True, verified=False, status="configured",
        )
        db.add(row)
        db.commit()
        connection_id = row.id

    async def confirmed(_row):
        return VerificationResult({"sender_id": 42})

    monkeypatch.setattr("app.routers.email_connections.verify_brevo_email", confirmed)
    token = create_access_token(user_id=user_id, tenant_id=tenant_id)
    response = client.post(
        f"/api/email-connections/{connection_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert response.json()["status"] == "active"

    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        db.delete(tenant)
        db.commit()
