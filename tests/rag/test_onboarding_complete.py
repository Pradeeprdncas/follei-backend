"""Onboarding item 9 regression: POST /complete does not block on pending review."""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config.database import SessionLocal
from app.core.security import create_access_token
from app.models.tenant import Tenant
from app.models.document import Document
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge import memory_store
from app.main import app

client = TestClient(app)


class _Collection:
    def __init__(self):
        self.rows = {}

    def find_one(self, key, projection=None):
        return self.rows.get((key["tenant_id"], key["subject_type"], key["subject_id"]))

    def replace_one(self, key, value, upsert=False):
        self.rows[(key["tenant_id"], key["subject_type"], key["subject_id"])] = value


@pytest.fixture
def ferretdb_collection(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(memory_store, "get_context_database", lambda: {"tenant_context": collection})
    return collection


@pytest.fixture
def tenant_and_token():
    db = SessionLocal()
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Complete Test Co", slug=f"complete-{tenant_id.hex[:8]}")
    db.add(tenant)
    db.commit()
    db.close()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    yield str(tenant_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM business_fact_drafts WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM documents WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM onboarding_goals WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM onboarding_contact_channels WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM onboarding_profiles WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_complete_without_profile_is_404(tenant_and_token, ferretdb_collection):
    _, token = tenant_and_token
    resp = client.post("/api/v1/onboarding/complete", headers=_auth(token))
    assert resp.status_code == 404


def test_complete_succeeds_with_unreviewed_extractions_pending(tenant_and_token, ferretdb_collection):
    tenant_id, token = tenant_and_token
    client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "SaaS", "goals": ["Increase Revenue"], "contact_channels": ["Email"]},
        headers=_auth(token),
    )
    db = SessionLocal()
    doc_id = uuid.uuid4()
    db.add(Document(id=doc_id, tenant_id=uuid.UUID(tenant_id), title="pricing.docx", source_type="docx", status="indexed"))
    db.commit()
    db.add(BusinessFactDraft(
        id=uuid.uuid4(), tenant_id=uuid.UUID(tenant_id), document_id=doc_id, fact_type="pricing",
        payload={"tier": "Pro"}, citation={}, approval_status="draft", created_at=datetime.utcnow(),
    ))
    db.commit()
    db.close()

    resp = client.post("/api/v1/onboarding/complete", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_completed"] is False
    assert body["pending_review_count"] == 1
    assert body["completed_at"] is not None


def test_complete_seeds_ferretdb_tenant_context(tenant_and_token, ferretdb_collection):
    tenant_id, token = tenant_and_token
    client.post(
        "/api/v1/onboarding/profile",
        json={"company_name": "Acme", "timezone": "Asia/Kolkata", "industry": "Healthcare", "goals": ["Reduce Customer Churn"], "contact_channels": ["SMS", "WhatsApp"]},
        headers=_auth(token),
    )
    client.post("/api/v1/onboarding/complete", headers=_auth(token))

    seeded = ferretdb_collection.rows.get((tenant_id, "tenant", tenant_id))
    assert seeded is not None
    assert seeded["industry"] == "Healthcare"
    assert seeded["goals"] == ["Reduce Customer Churn"]
    assert sorted(seeded["contact_channels"]) == ["SMS", "WhatsApp"]


def test_complete_is_idempotent(tenant_and_token, ferretdb_collection):
    _, token = tenant_and_token
    client.post("/api/v1/onboarding/profile", json={"company_name": "Acme", "timezone": "Asia/Kolkata"}, headers=_auth(token))
    first = client.post("/api/v1/onboarding/complete", headers=_auth(token))
    second = client.post("/api/v1/onboarding/complete", headers=_auth(token))
    assert first.json()["already_completed"] is False
    assert second.json()["already_completed"] is True
    assert first.json()["completed_at"] == second.json()["completed_at"]
