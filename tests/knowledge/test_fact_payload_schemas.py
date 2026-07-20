"""Every supported business category has a minimum publishable payload."""
import pytest

from app.services.knowledge.fact_extraction import validate_fact_payload


@pytest.mark.parametrize(("fact_type", "payload"), [
    ("product", {"name": "Follei AI"}),
    ("service", {"name": "Implementation"}),
    ("pricing", {"name": "Enterprise", "tiers": [{"price": 999}]}),
    ("plan", {"name": "Enterprise"}),
    ("policy", {"title": "Refund policy", "body": "Refunds are available for 45 days."}),
    ("faq", {"question": "How long?", "answer": "45 days."}),
    ("competitor", {"name": "Example Corp"}),
    ("customer_segment", {"name": "Enterprise buyers"}),
    ("sales_process", {"name": "Discovery", "steps": ["Qualify"]}),
    ("support_process", {"name": "Escalation", "description": "Escalate P1 incidents."}),
    ("payment_process", {"name": "Invoice collection", "description": "Send invoice monthly."}),
])
def test_all_fact_types_accept_minimum_publishable_schema(fact_type, payload):
    assert validate_fact_payload(fact_type, payload) is None


@pytest.mark.parametrize(("fact_type", "payload", "message"), [
    ("pricing", {"name": "Enterprise"}, "price"),
    ("policy", {"title": "Refund"}, "body"),
    ("faq", {"question": "How?"}, "answer"),
    ("customer_segment", {}, "name"),
    ("sales_process", {"name": "Discovery"}, "description or steps"),
])
def test_malformed_fact_payloads_are_rejected(fact_type, payload, message):
    assert message in (validate_fact_payload(fact_type, payload) or "")
