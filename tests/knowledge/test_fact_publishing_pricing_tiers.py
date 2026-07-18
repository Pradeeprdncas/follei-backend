"""Regression: publish_fact_draft() must not silently drop price data.

The real (LLM) extraction path emits a flat pricing payload
({"tier": ..., "price": ..., "billing_frequency": ..., "billing_term": ...}),
not the {"tiers": [...]} shape the fallback extractor produces. The bug: the
publisher only ever read payload["tiers"], so every real pricing approval
published with an empty tiers list.
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.config.database import SessionLocal
from app.models.tenant import Tenant
from app.models.document import Document
from app.models.domain import PricingModel
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.fact_publishing import publish_fact_draft, _normalize_pricing_tiers


def test_normalize_pricing_tiers_handles_flat_llm_shape():
    flat_payload = {"tier": "Enterprise", "price": 999, "billing_frequency": "monthly", "billing_term": "annually"}
    assert _normalize_pricing_tiers(flat_payload) == [
        {"price": 999, "billing_frequency": "monthly", "billing_term": "annually", "name": "Enterprise"}
    ]


def test_normalize_pricing_tiers_still_handles_structured_tiers_list():
    structured_payload = {"tiers": [{"name": "Basic", "price": 10}, {"name": "Pro", "price": 50}]}
    assert _normalize_pricing_tiers(structured_payload) == structured_payload["tiers"]


def test_normalize_pricing_tiers_empty_payload_returns_empty_list():
    assert _normalize_pricing_tiers({}) == []


@pytest.fixture
def seeded_pricing_draft():
    db = SessionLocal()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Fact Publish Test Co", slug=f"factpub-{tenant_id.hex[:8]}"))
    db.commit()
    db.add(Document(id=doc_id, tenant_id=tenant_id, title="pricing.docx", source_type="docx", status="indexed"))
    db.commit()
    # This is the real shape the LLM extractor produces (see fact_extraction.py's
    # prompt: no fixed schema for "pricing" payload is enforced), not the
    # fallback extractor's {"tiers": [...]} shape.
    draft = BusinessFactDraft(
        id=draft_id, tenant_id=tenant_id, document_id=doc_id, fact_type="pricing",
        payload={"tier": "Enterprise", "price": 999, "billing_frequency": "monthly", "billing_term": "annually"},
        citation={"document_name": "pricing.docx"}, extraction_confidence=0.95,
        approval_status="draft", created_at=datetime.utcnow(),
    )
    db.add(draft)
    db.commit()
    db.close()
    yield tenant_id, draft_id
    db = SessionLocal()
    db.execute(text("DELETE FROM pricing_models WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM business_fact_drafts WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM documents WHERE tenant_id = :t"), {"t": str(tenant_id)})
    db.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
    db.commit()
    db.close()


def test_publish_real_pricing_draft_retains_price_data_in_db(seeded_pricing_draft, capsys):
    tenant_id, draft_id = seeded_pricing_draft
    db = SessionLocal()

    before_row = db.execute(text("SELECT id, name, tiers FROM pricing_models WHERE tenant_id = :t"), {"t": str(tenant_id)}).first()
    print(f"BEFORE publish: pricing_models row = {before_row}")
    assert before_row is None

    draft = db.query(BusinessFactDraft).filter(BusinessFactDraft.id == draft_id).with_for_update().first()
    record = publish_fact_draft(db, draft)
    record_tiers_before_close = record.tiers
    draft.approval_status = "approved"
    db.commit()

    after_row = db.execute(text("SELECT id, name, tiers FROM pricing_models WHERE tenant_id = :t"), {"t": str(tenant_id)}).first()
    print(f"AFTER publish: pricing_models row = {after_row}")
    db.close()

    assert after_row is not None
    assert after_row.tiers == [{"price": 999, "billing_frequency": "monthly", "billing_term": "annually", "name": "Enterprise"}]
    assert record_tiers_before_close == after_row.tiers
