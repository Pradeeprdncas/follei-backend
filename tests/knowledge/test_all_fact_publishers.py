from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.fact_extraction import _fallback_facts, validate_fact_payload
from app.services.knowledge.fact_publishing import publish_fact_draft


class Session:
    def __init__(self): self.added = []
    def add(self, value): self.added.append(value)
    def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None: value.id = uuid4()


@pytest.mark.parametrize(("fact_type", "payload", "table"), [
    ("product", {"name": "Product"}, "products"),
    ("service", {"name": "Service"}, "services"),
    ("pricing", {"name": "Enterprise", "tiers": [{"price": 999}]}, "pricing_models"),
    ("plan", {"name": "Enterprise"}, "business_plans"),
    ("policy", {"title": "Refund", "body": "45 days"}, "policies"),
    ("faq", {"question": "Window?", "answer": "45 days"}, "faqs"),
    ("competitor", {"name": "Competitor"}, "competitors"),
    ("customer_segment", {"name": "Enterprise"}, "customer_segments"),
    ("sales_process", {"name": "Sales", "steps": ["Qualify"]}, "procedures"),
    ("support_process", {"name": "Support", "description": "Escalate"}, "procedures"),
    ("payment_process", {"name": "Payment", "description": "Invoice"}, "procedures"),
])
def test_every_review_category_publishes_to_operational_table(fact_type, payload, table):
    draft = BusinessFactDraft(id=uuid4(), tenant_id=uuid4(), document_id=uuid4(), chunk_id=uuid4(), fact_type=fact_type, payload=payload, citation={"document_id": "doc"}, approval_status="draft")
    record = publish_fact_draft(Session(), draft)
    assert record.__tablename__ == table
    assert record.tenant_id == draft.tenant_id
    assert draft.published_record_id == record.id


@pytest.mark.parametrize(("category", "fact_type", "heading", "text"), [
    ("product", "product", "Follei Core", "Follei Core automates business workflows."),
    ("service", "service", "Implementation Service", "We provide implementation support."),
    ("pricing", "pricing", "Enterprise Pricing", "Enterprise costs $999 per month."),
    ("plan", "plan", "Enterprise Plan", "Enterprise Plan includes priority support."),
    ("policy", "policy", "Refund Policy", "Refund requests are accepted for 45 days."),
    ("faq", "faq", "How long is the refund window?", "The refund window is 45 days."),
    ("competitor", "competitor", "Example Competitor", "Example Competitor serves the same market."),
    ("customer_segment", "customer_segment", "Enterprise Teams", "Enterprise teams with 100 seats."),
    ("sales_process", "sales_process", "Sales Qualification", "Qualify, discover, propose, and close."),
    ("support_process", "support_process", "Support Escalation", "Triage and escalate severity-one tickets."),
    ("payment_process", "payment_process", "Invoice Collection", "Issue an invoice and reconcile payment."),
])
def test_every_category_has_deterministic_extraction_and_operational_publish(category, fact_type, heading, text):
    document = SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), title=f"{category}.txt", category=category,
        source_uri=f"upload://{category}.txt", version=1,
    )
    chunk = SimpleNamespace(id=uuid4(), text=text, page=1, heading=heading, section_path=[heading])
    extracted = next(item for item in _fallback_facts(document, [chunk]) if item["fact_type"] == fact_type)

    assert validate_fact_payload(fact_type, extracted["payload"]) is None
    draft = BusinessFactDraft(
        id=uuid4(), tenant_id=document.tenant_id, document_id=document.id, chunk_id=chunk.id,
        fact_type=fact_type, payload=extracted["payload"], citation={"document_id": str(document.id)},
        approval_status="draft",
    )

    record = publish_fact_draft(Session(), draft)

    assert record.tenant_id == document.tenant_id
    assert draft.published_record_id == record.id
