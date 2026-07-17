from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge import fact_extraction
from app.services.knowledge.fact_publishing import publish_fact_draft


class _Query:
    def filter(self, *args):
        return self

    def first(self):
        return None


class _DraftSession:
    def __init__(self):
        self.added = []

    def query(self, *args):
        return _Query()

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass

    def refresh(self, value):
        if value.id is None:
            value.id = uuid4()


class _PublishSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


@pytest.mark.asyncio
async def test_pricing_document_creates_cited_draft_without_publishing(monkeypatch):
    async def no_llm(*args, **kwargs):
        return []

    monkeypatch.setattr(fact_extraction, "_llm_facts", no_llm)
    tenant_id, document_id, chunk_id = uuid4(), uuid4(), uuid4()
    document = SimpleNamespace(
        id=document_id, tenant_id=tenant_id, title="Enterprise pricing.pdf", category="pricing",
        source_uri="upload://tenant-a/enterprise-pricing.pdf", version=1,
    )
    chunk = SimpleNamespace(
        id=chunk_id, text="Enterprise | $30,000 | 100 seats", page=2,
        heading="Enterprise", section_path=["Pricing", "Enterprise"],
    )
    db = _DraftSession()

    drafts = await fact_extraction.extract_document_facts(db, document=document, chunks=[chunk])

    assert len(drafts) == 1
    assert drafts[0].fact_type == "pricing"
    assert drafts[0].approval_status == "draft"
    assert drafts[0].citation["document_id"] == str(document_id)
    assert drafts[0].citation["heading_path"] == ["Pricing", "Enterprise"]
    assert all(not getattr(value, "__tablename__", "").startswith("pricing_models") for value in db.added)


def test_approve_pricing_draft_publishes_record_with_immutable_citation_link():
    tenant_id = uuid4()
    draft = BusinessFactDraft(
        id=uuid4(), tenant_id=tenant_id, document_id=uuid4(), chunk_id=uuid4(),
        fact_type="pricing", payload={"name": "Enterprise", "model_type": "annual", "tiers": [{"price": 30000}]},
        citation={"document_id": "source-doc", "page": 2, "heading_path": ["Pricing", "Enterprise"]},
        approval_status="draft",
    )
    db = _PublishSession()

    record = publish_fact_draft(db, draft)

    assert record.__tablename__ == "pricing_models"
    assert record.tenant_id == tenant_id
    assert record.metadata_["fact_draft_id"] == str(draft.id)
    assert record.metadata_["source_citation"]["document_id"] == "source-doc"
    assert draft.published_record_type == "pricing_models"
    assert draft.published_record_id == record.id


def test_fact_publishing_never_crosses_tenant_boundary():
    draft = BusinessFactDraft(
        id=uuid4(), tenant_id=uuid4(), document_id=uuid4(), chunk_id=uuid4(),
        fact_type="product", payload={"name": "Follei"}, citation={"document_id": "source"}, approval_status="draft",
    )
    db = _PublishSession()

    record = publish_fact_draft(db, draft)

    assert record.tenant_id == draft.tenant_id
