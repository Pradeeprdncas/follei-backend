"""PostgreSQL contract tests for the tenant-scoped onboarding aggregate."""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all relationships before ORM inserts
from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id
from app.models.knowledge.document import KnowledgeSource
from app.models.tenancy import Tenant
from app.routers.onboarding_state import router
from app.services.knowledge.categories import CATEGORY_DEFINITIONS


@pytest.fixture()
def onboarding_client():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL contract tests")

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    tenant_a = Tenant(id=uuid.uuid4(), name=f"contract-a-{uuid.uuid4()}")
    tenant_b = Tenant(id=uuid.uuid4(), name=f"contract-b-{uuid.uuid4()}")
    source_a = KnowledgeSource(
        id=uuid.uuid4(), tenant_id=tenant_a.id, name="Tenant A website",
        source_type="website", status="active", config={"url": "https://a.example"},
    )
    source_b = KnowledgeSource(
        id=uuid.uuid4(), tenant_id=tenant_b.id, name="Tenant B website",
        source_type="website", status="active", config={"url": "https://b.example"},
    )
    db.add_all([tenant_a, tenant_b, source_a, source_b])
    db.commit()

    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_authenticated_tenant_id] = lambda: str(tenant_a.id)
    client = TestClient(api)
    try:
        yield client, tenant_a, tenant_b, source_a, source_b
    finally:
        client.close()
        db.rollback()
        db.execute(
            text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
            {"tenant_a": tenant_a.id, "tenant_b": tenant_b.id},
        )
        db.commit()
        db.close()
        engine.dispose()


def test_onboarding_state_contract_shape(onboarding_client):
    client, *_ = onboarding_client

    response = client.get("/api/v1/onboarding/state")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta", "errors"}
    assert set(body["meta"]) >= {"request_id", "generated_at"}
    assert body["errors"] == []
    assert set(body["data"]) == {
        "step", "progress", "sources", "runs", "category_summaries",
        "missing_data", "important_missing_data", "confirmations_needed",
        "confirmations", "can_continue", "ready_for_autonomous_actions",
    }
    assert len(body["data"]["category_summaries"]) == len(CATEGORY_DEFINITIONS)
    assert body["data"]["progress"]["categories_total"] == len(CATEGORY_DEFINITIONS)


def test_onboarding_state_is_tenant_isolated(onboarding_client):
    client, tenant_a, tenant_b, source_a, source_b = onboarding_client

    state = client.get("/api/v1/onboarding/state").json()["data"]

    assert [row["id"] for row in state["sources"]] == [str(source_a.id)]
    serialized = str(state)
    assert str(tenant_b.id) not in serialized
    assert str(source_b.id) not in serialized
    assert "Tenant B website" not in serialized
    assert "https://b.example" not in serialized
    assert state["sources"][0]["config"]["url"] == "https://a.example"
    assert str(tenant_a.id) not in state["sources"][0]
