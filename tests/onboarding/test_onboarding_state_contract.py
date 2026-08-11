"""PostgreSQL contract tests for the tenant-scoped onboarding aggregate."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register all relationships before ORM inserts
from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id
from app.models.knowledge.document import Document, KnowledgeSource
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.ingestion import CategorySummary
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.models.knowledge.indexing_job import IndexingJob
from app.models.tenancy import Tenant
from app.routers.onboarding_state import router
from app.services.knowledge.categories import CATEGORY_DEFINITIONS
from app.services.knowledge.category_summaries import refresh_category_summaries
from app.services.knowledge.run_status import reconcile_ingestion_run


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
    assert all("display" in row for row in body["data"]["category_summaries"])
    products = next(row for row in body["data"]["category_summaries"] if row["key"] == "products")
    assert products["display"] == {
        "mode": "enumerable",
        "items_endpoint": "/api/v1/onboarding/categories/products/items",
        "review_progress": {"reviewed": 0, "total": 0},
    }


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


def test_onboarding_state_surfaces_downstream_ingestion_job_failures(onboarding_client):
    client, tenant_a, _tenant_b, source_a, _source_b = onboarding_client
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        run = IngestionRun(
            id=uuid.uuid4(), tenant_id=tenant_a.id, source_id=source_a.id,
            status="failed", error="One or more indexing jobs failed",
        )
        crawl = SourceIngestionJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, run_id=run.id,
            job_type="website_crawl", target="https://a.example",
            status="completed", attempt=1,
        )
        indexing = IndexingJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, status="dead_lettered",
            attempt_count=3, last_error="Vector dimension mismatch",
            payload={"source_metadata": {"ingestion_run_id": str(run.id)}},
        )
        db.add_all([run, crawl, indexing])
        db.commit()
        run_id = str(run.id)
        crawl_id = str(crawl.id)
        indexing_id = str(indexing.id)

    state = client.get("/api/v1/onboarding/state").json()["data"]
    row = next(item for item in state["runs"] if item["id"] == run_id)
    assert row["status"] == "failed"
    assert row["jobs"] == [
        {
            "id": crawl_id, "type": "website_crawl", "status": "completed",
            "attempt": 1, "error": None, "progress": {},
        },
        {
            "id": indexing_id, "type": "document_indexing", "status": "dead_lettered",
            "attempt": 3, "error": "Document indexing failed",
        },
    ]
    assert "Vector dimension mismatch" not in str(row)


def test_run_snapshot_and_stream_return_source_specific_results(onboarding_client):
    client, tenant_a, tenant_b, source_a, source_b = onboarding_client
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        run_a = IngestionRun(
            id=uuid.uuid4(), tenant_id=tenant_a.id, source_id=source_a.id,
            status="completed", page_count=2, document_count=1,
            started_at=datetime.utcnow(), completed_at=datetime.utcnow(),
        )
        crawl_a = SourceIngestionJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, run_id=run_a.id,
            job_type="website_crawl", status="completed", attempt=1,
            payload={
                "stage": "indexing", "pages_discovered": 2,
                "documents_discovered": 1, "items_queued": 1,
                "internal_secret": "must-not-leak",
            },
        )
        document_a = Document(
            id=uuid.uuid4(), tenant_id=tenant_a.id, source_id=source_a.id,
            title="Pricing", source_type="txt", source_uri="https://a.example/pricing",
            status="ready", category="pricing", primary_category="pricing",
            summary="Tenant A plans", metadata_={"total_chunks": 3},
        )
        index_a = IndexingJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, document_id=document_a.id,
            status="indexed", attempt_count=1,
            payload={"source_metadata": {"ingestion_run_id": str(run_a.id)}},
        )
        fact_a = BusinessFactDraft(
            tenant_id=tenant_a.id, document_id=document_a.id, fact_type="pricing",
            payload={"name": "Growth plan"}, citation={}, approval_status="draft",
        )
        run_b = IngestionRun(
            id=uuid.uuid4(), tenant_id=tenant_b.id, source_id=source_b.id,
            status="completed",
        )
        db.add_all([run_a, crawl_a, document_a, index_a, fact_a, run_b])
        db.commit()
        run_a_id, run_b_id = str(run_a.id), str(run_b.id)

    response = client.get(f"/api/v1/onboarding/runs/{run_a_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["terminal"] is True
    assert data["progress_percent"] == 100
    assert data["counts"] == {
        "pages_discovered": 2,
        "documents_discovered": 1,
        "records_discovered": 0,
        "items_queued": 1,
        "documents_indexed": 1,
        "categories_found": 1,
        "items_extracted": 1,
    }
    assert data["jobs"][0]["progress"] == {
        "stage": "indexing", "pages_discovered": 2,
        "documents_discovered": 1, "items_queued": 1,
    }
    assert "internal_secret" not in str(data)
    assert data["results"]["documents"][0]["title"] == "Pricing"
    assert data["results"]["categories"][0]["sample_items"] == ["Growth plan"]
    assert str(tenant_b.id) not in str(data)

    with client.stream("GET", f"/api/v1/onboarding/runs/{run_a_id}/events") as streamed:
        body = "".join(streamed.iter_text())
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: complete" in body
    assert '"terminal":true' in body

    assert client.get(f"/api/v1/onboarding/runs/{run_b_id}").status_code == 404
    assert client.get(f"/api/v1/onboarding/runs/{run_b_id}/events").status_code == 404
    engine.dispose()


def test_google_run_cannot_finish_while_a_resource_job_is_still_active(onboarding_client):
    _client, tenant_a, _tenant_b, source_a, _source_b = onboarding_client
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        run = IngestionRun(
            id=uuid.uuid4(), tenant_id=tenant_a.id, source_id=source_a.id,
            status="running",
        )
        gmail = SourceIngestionJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, run_id=run.id,
            job_type="google_gmail_sync", status="completed", payload={"items_queued": 1},
        )
        drive = SourceIngestionJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, run_id=run.id,
            job_type="google_drive_sync", status="running", payload={"items_queued": 1},
        )
        gmail_index = IndexingJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, status="indexed",
            payload={"source_metadata": {"ingestion_run_id": str(run.id)}},
        )
        db.add_all([run, gmail, drive, gmail_index])
        db.commit()

        reconcile_ingestion_run(db, run)
        assert run.status == "running"
        assert run.completed_at is None

        drive.status = "completed"
        drive_index = IndexingJob(
            id=uuid.uuid4(), tenant_id=tenant_a.id, status="indexed",
            payload={"source_metadata": {"ingestion_run_id": str(run.id)}},
        )
        db.add(drive_index)
        db.commit()
        reconcile_ingestion_run(db, run)
        assert run.status == "completed"
        assert run.completed_at is not None
    engine.dispose()


def test_category_items_are_paginated_and_tenant_isolated(onboarding_client):
    client, tenant_a, tenant_b, *_ = onboarding_client
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    document_a = Document(id=uuid.uuid4(), tenant_id=tenant_a.id, title="a.json", source_type="json", status="indexed")
    document_b = Document(id=uuid.uuid4(), tenant_id=tenant_b.id, title="b.json", source_type="json", status="indexed")
    db.add_all([document_a, document_b])
    db.commit()
    db.add_all([
        BusinessFactDraft(
            tenant_id=tenant_a.id, document_id=document_a.id, fact_type="product",
            payload={"name": "Tenant A product"}, citation={}, approval_status="draft",
            item_review_status="edited", created_at=datetime.utcnow(),
        ),
        BusinessFactDraft(
            tenant_id=tenant_b.id, document_id=document_b.id, fact_type="product",
            payload={"name": "Tenant B secret"}, citation={}, approval_status="draft",
            item_review_status="pending", created_at=datetime.utcnow(),
        ),
    ])
    db.commit()
    refresh_category_summaries(db, tenant_a.id)
    db.close()
    engine.dispose()

    response = client.get("/api/v1/onboarding/categories/products/items?page=1&page_size=1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"] == {"page": 1, "page_size": 1, "total": 1, "pages": 1}
    assert data["items"][0]["payload"] == {"name": "Tenant A product"}
    assert data["items"][0]["review_status"] == "edited"
    assert "Tenant B secret" not in str(data)
    state = client.get("/api/v1/onboarding/state").json()["data"]
    products = next(row for row in state["category_summaries"] if row["key"] == "products")
    assert products["display"]["review_progress"] == {"reviewed": 1, "total": 1}


def test_state_remains_fast_with_more_than_8000_category_items(onboarding_client):
    client, tenant_a, *_ = onboarding_client
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    document = Document(id=uuid.uuid4(), tenant_id=tenant_a.id, title="large.json", source_type="json", status="indexed")
    db.add(document)
    db.commit()
    now = datetime.utcnow()
    db.execute(insert(BusinessFactDraft), [
        {
            "id": uuid.uuid4(), "tenant_id": tenant_a.id, "document_id": document.id,
            "fact_type": "product", "payload": {"name": f"SKU {index}"}, "citation": {},
            "approval_status": "draft", "item_review_status": "pending", "created_at": now,
        }
        for index in range(8001)
    ])
    db.add(CategorySummary(
        tenant_id=tenant_a.id, category_key="products", category_group="business",
        status="found", item_count=8001, summary="8,001 products found.", confidence=0.9,
        needs_review=False, display_mode="aggregate", breakdown=[{"label": "Catalog", "count": 8001}],
        sample_items=["SKU 0", "SKU 1", "SKU 2"], reviewed_count=0,
    ))
    db.commit()
    db.close()

    statements: list[str] = []
    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(Engine, "before_cursor_execute", capture_statement)
    started = time.perf_counter()
    response = client.get("/api/v1/onboarding/state")
    elapsed = time.perf_counter() - started
    event.remove(Engine, "before_cursor_execute", capture_statement)
    engine.dispose()

    assert response.status_code == 200
    products = next(row for row in response.json()["data"]["category_summaries"] if row["key"] == "products")
    assert products["count"] == 8001
    assert products["display"]["mode"] == "aggregate"
    assert "items" not in products["display"]
    assert elapsed < 1.0, f"state endpoint took {elapsed:.3f}s with 8,001 items"
    # The state path must stay on its materialized PostgreSQL summary and never
    # scan the large fact table.
    assert not any("business_fact_drafts" in statement for statement in statements)
