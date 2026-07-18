"""Onboarding item 6 regression: extraction-review grouping over business_fact_drafts."""
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.models.tenant import Tenant
from app.models.document import Document
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.extraction_review import group_extractions_by_category, ALL_CATEGORIES


@pytest.fixture
def seeded_tenant():
    db: Session = SessionLocal()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Extractions Co", slug=f"ext-{tenant_id.hex[:8]}"))
    db.commit()
    db.add(Document(id=doc_id, tenant_id=tenant_id, title="policy.docx", source_type="docx", status="indexed"))
    db.commit()

    def draft(fact_type, status="draft"):
        return BusinessFactDraft(
            id=uuid.uuid4(), tenant_id=tenant_id, document_id=doc_id, fact_type=fact_type,
            payload={"name": fact_type}, citation={"document_name": "policy.docx"},
            extraction_confidence=0.8, approval_status=status, created_at=datetime.utcnow(),
        )

    db.add_all([
        draft("pricing"),
        draft("product"),
        draft("product"),
        draft("faq", status="approved"),  # not draft-status, should not show under default filter
    ])
    db.commit()
    db.close()
    yield tenant_id, doc_id

    db = SessionLocal()
    db.query(BusinessFactDraft).filter(BusinessFactDraft.tenant_id == tenant_id).delete()
    db.query(Document).filter(Document.tenant_id == tenant_id).delete()
    db.query(Tenant).filter(Tenant.id == tenant_id).delete()
    db.commit()
    db.close()


def test_groups_drafts_into_ui_categories(seeded_tenant):
    tenant_id, _ = seeded_tenant
    db = SessionLocal()
    grouped = group_extractions_by_category(db, tenant_id)
    db.close()

    assert set(grouped.keys()) == set(ALL_CATEGORIES)
    assert len(grouped["Pricing"]) == 1
    assert len(grouped["Products"]) == 2
    assert grouped["Plans"] == []  # no fact_type maps to it yet
    assert grouped["FAQs"] == []  # the one faq draft is status=approved, excluded by default


def test_citation_is_included_per_item(seeded_tenant):
    tenant_id, _ = seeded_tenant
    db = SessionLocal()
    grouped = group_extractions_by_category(db, tenant_id)
    db.close()
    assert grouped["Pricing"][0]["citation"]["document_name"] == "policy.docx"


def test_status_filter_can_show_approved_items(seeded_tenant):
    tenant_id, _ = seeded_tenant
    db = SessionLocal()
    grouped = group_extractions_by_category(db, tenant_id, status="approved")
    db.close()
    assert len(grouped["FAQs"]) == 1
    assert grouped["Pricing"] == []
