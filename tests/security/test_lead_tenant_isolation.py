import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.routers import leads


def _headers(tenant_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


def test_tenant_cannot_list_read_or_mutate_another_tenants_lead():
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    api = FastAPI()
    api.include_router(leads.router, prefix="/api")
    client = TestClient(api)
    leads.LEADS.clear()
    try:
        created_a = client.post(
            "/api/leads",
            headers=_headers(tenant_a),
            json={"email": "a@example.com", "tenant_id": str(tenant_a)},
        )
        created_b = client.post(
            "/api/leads",
            headers=_headers(tenant_b),
            json={"email": "b@example.com", "tenant_id": str(tenant_b)},
        )
        assert created_a.status_code == created_b.status_code == 201
        lead_a = created_a.json()["id"]
        lead_b = created_b.json()["id"]

        listed = client.get("/api/leads", headers=_headers(tenant_a))
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [lead_a]
        assert client.get(f"/api/leads/{lead_b}", headers=_headers(tenant_a)).status_code == 404
        assert client.patch(f"/api/leads/{lead_b}", headers=_headers(tenant_a), json={"status": "qualified"}).status_code == 404
        assert client.delete(f"/api/leads/{lead_b}", headers=_headers(tenant_a)).status_code == 404
        assert client.get("/api/leads", params={"tenant_id": str(tenant_b)}, headers=_headers(tenant_a)).status_code == 403
    finally:
        leads.LEADS.clear()
        client.close()
