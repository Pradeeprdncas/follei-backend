"""Adaptive category display boundaries and materialization behavior."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.models.knowledge.document import Document
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.ingestion import CategorySummary
from app.models.tenancy import Tenant
from app.services.knowledge.categories import review_mode_for_category
from app.services.knowledge.category_summaries import refresh_category_summaries


class FakeSummaryLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, prompt: str, stream: bool = True):
        self.calls += 1
        assert stream is False
        assert '"item_count": 26' in prompt
        yield json.dumps({
            "categories": [{
                "key": "products",
                "summary": "26 products across two naturally detected types.",
                "breakdown": [
                    {"label": "Electronics", "count": 13},
                    {"label": "Accessories", "count": 13},
                ],
                "sample_items": ["Product 0", "Product 1", "Product 2"],
            }]
        })


@pytest.mark.parametrize(
    ("category", "count", "expected"),
    [
        ("products", 25, "enumerable"),
        ("products", 26, "aggregate"),
        ("policies_terms", 10_000, "enumerable"),
        ("listings", 10_000, "enumerable"),
        ("contracts", 10_000, "enumerable"),
        ("pricing_packages", 10_000, "enumerable"),
    ],
)
def test_review_mode_threshold_and_forced_overrides(category, count, expected):
    assert review_mode_for_category(category, count, threshold=25) == expected


def test_aggregate_summary_is_generated_and_materialized_by_llm():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL materialization test")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    tenant = Tenant(id=uuid.uuid4(), name=f"adaptive-{uuid.uuid4()}")
    document = Document(
        id=uuid.uuid4(), tenant_id=tenant.id, title="catalog.json",
        source_type="json", status="indexed",
    )
    db.add(tenant)
    db.commit()
    db.add(document)
    db.commit()
    db.add_all([
        BusinessFactDraft(
            id=uuid.uuid4(), tenant_id=tenant.id, document_id=document.id,
            fact_type="product", payload={"name": f"Product {index}", "type": "Electronics" if index % 2 == 0 else "Accessories"},
            citation={"document_name": "catalog.json"}, extraction_confidence=0.9,
            approval_status="draft", item_review_status="pending", created_at=datetime.utcnow(),
        )
        for index in range(26)
    ])
    db.commit()
    llm = FakeSummaryLLM()
    try:
        refresh_category_summaries(db, tenant.id, llm_service=llm)
        row = db.query(CategorySummary).filter_by(tenant_id=tenant.id, category_key="products").one()
        assert llm.calls == 1
        assert row.display_mode == "aggregate"
        assert row.item_count == 26
        assert row.summary == "26 products across two naturally detected types."
        assert row.breakdown == [
            {"label": "Electronics", "count": 13},
            {"label": "Accessories", "count": 13},
        ]
        assert row.sample_items == ["Product 0", "Product 1", "Product 2"]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": tenant.id})
        db.commit()
        db.close()
        engine.dispose()
