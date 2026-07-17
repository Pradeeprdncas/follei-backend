"""Fix 3 regression: tenant_id must come from the JWT, not the request body/query.

Policy: reject-on-mismatch. A caller authenticated as tenant A who supplies
tenant B's UUID anywhere in the request must get 403, never tenant B's data.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core.security import create_access_token
from app.main import app

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
USER_A = uuid.uuid4()


class _FakeDB:
    """Minimal stand-in so dependency resolution doesn't hit a real database."""

    def query(self, *_a, **_k):
        raise AssertionError("Handler reached the database after a tenant mismatch should have rejected it")

    def close(self):
        pass


def _override_get_db():
    yield _FakeDB()


@pytest.fixture(autouse=True)
def _db_override():
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def _auth_header(tenant_id: uuid.UUID) -> dict:
    token = create_access_token(user_id=USER_A, tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


client = TestClient(app)


def test_upload_rejects_mismatched_tenant():
    resp = client.post(
        "/upload/",
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"tenant_id": str(TENANT_B)},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_chat_rejects_mismatched_tenant():
    resp = client.post(
        "/chat/",
        json={"question": "What is the refund window?", "tenant_id": str(TENANT_B)},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_orchestrator_context_rejects_mismatched_tenant():
    resp = client.post(
        "/knowledge/orchestrator/context",
        json={"tenant_id": str(TENANT_B), "query": "pricing"},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_list_fact_drafts_rejects_mismatched_tenant():
    resp = client.get(
        "/knowledge/review/facts/drafts",
        params={"tenant_id": str(TENANT_B)},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_approve_fact_draft_rejects_mismatched_tenant():
    draft_id = uuid.uuid4()
    resp = client.post(
        f"/knowledge/review/facts/{draft_id}/approve",
        json={"tenant_id": str(TENANT_B), "reviewer": "human"},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_persist_turn_rejects_mismatched_tenant():
    resp = client.post(
        "/knowledge/conversations/turns",
        json={
            "tenant_id": str(TENANT_B),
            "channel": "chat",
            "direction": "inbound",
            "speaker": "customer",
            "text": "hello",
        },
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 403


def test_missing_bearer_token_is_rejected():
    resp = client.post(
        "/knowledge/orchestrator/context",
        json={"tenant_id": str(TENANT_A), "query": "pricing"},
    )
    assert resp.status_code == 401


def test_matching_tenant_is_not_rejected_by_auth_layer(monkeypatch):
    """A valid JWT whose tenant matches the request must pass the auth check
    (it may still fail deeper in the pipeline, but never with 401/403)."""
    from app.services.rag.pipelines import chat as chat_module

    async def fake_chat_pipeline(**_kwargs):
        return {"answer": "ok", "citations": [], "confidence": 0.9, "supported": True, "reason": "test"}

    monkeypatch.setattr(chat_module, "chat_pipeline", AsyncMock(side_effect=fake_chat_pipeline))
    # chat.py imported chat_pipeline by reference at module load time, patch that binding too.
    from app.routers import chat as chat_router
    monkeypatch.setattr(chat_router, "chat_pipeline", fake_chat_pipeline)

    resp = client.post(
        "/chat/",
        json={"question": "What is the refund window?", "tenant_id": str(TENANT_A)},
        headers=_auth_header(TENANT_A),
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "ok"
