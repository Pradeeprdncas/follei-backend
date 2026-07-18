"""Onboarding item 7 regression: edit a draft fact before approving it."""
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
from app.main import app

client = TestClient(app)


@pytest.fixture
def seeded_draft():
    db = SessionLocal()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Edit Draft Co", slug=f"edit-{tenant_id.hex[:8]}"))
    db.commit()
    db.add(Document(id=doc_id, tenant_id=tenant_id, title="pricing.docx", source_type="docx", status="indexed"))
    db.commit()
    db.add(BusinessFactDraft(
        id=draft_id, tenant_id=tenant_id, document_id=doc_id, fact_type="pricing",
        payload={"tier": "Enterprise", "price": 999}, citation={"document_name": "pricing.docx"},
        extraction_confidence=0.9, approval_status="draft", created_at=datetime.utcnow(),
    ))
    db.commit()
    db.close()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=tenant_id)
    yield str(tenant_id), str(draft_id), token
    db = SessionLocal()
    db.execute(text("DELETE FROM business_fact_drafts WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM documents WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_edit_updates_payload_and_stays_draft(seeded_draft):
    _, draft_id, token = seeded_draft
    resp = client.patch(
        f"/api/v1/onboarding/extractions/{draft_id}",
        json={"payload": {"tier": "Enterprise", "price": 1099}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["payload"]["price"] == 1099
    assert body["approval_status"] == "draft"


def test_edited_then_approved_publishes_the_edited_value(seeded_draft):
    tenant_id, draft_id, token = seeded_draft
    client.patch(
        f"/api/v1/onboarding/extractions/{draft_id}",
        json={"payload": {"tier": "Enterprise", "price": 1099}},
        headers=_auth(token),
    )
    resp = client.post(
        f"/knowledge/review/facts/{draft_id}/approve",
        json={"tenant_id": tenant_id, "reviewer": "test"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["payload"]["price"] == 1099
    assert resp.json()["approval_status"] == "approved"


def test_cannot_edit_an_already_approved_draft(seeded_draft):
    tenant_id, draft_id, token = seeded_draft
    client.post(f"/knowledge/review/facts/{draft_id}/approve", json={"tenant_id": tenant_id, "reviewer": "test"}, headers=_auth(token))
    resp = client.patch(
        f"/api/v1/onboarding/extractions/{draft_id}",
        json={"payload": {"tier": "Enterprise", "price": 1}},
        headers=_auth(token),
    )
    assert resp.status_code == 409


def test_edit_of_unknown_draft_is_404(seeded_draft):
    _, _, token = seeded_draft
    resp = client.patch(
        f"/api/v1/onboarding/extractions/{uuid.uuid4()}",
        json={"payload": {"x": 1}},
        headers=_auth(token),
    )
    assert resp.status_code == 404
