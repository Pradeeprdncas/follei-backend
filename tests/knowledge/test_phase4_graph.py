from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.knowledge import graph


def test_approved_fact_creates_cited_business_graph_relations(monkeypatch):
    entities, relation_calls = {}, []

    def fake_entity(db, *, tenant_id, entity_type, name, metadata=None):
        key = (str(tenant_id), entity_type, name)
        return entities.setdefault(key, SimpleNamespace(id=uuid4(), name=name, entity_type=entity_type, metadata_=metadata or {}))

    def fake_relation(db, *, tenant_id, source, target, relation_type, metadata=None):
        relation_calls.append((str(tenant_id), source.name, relation_type, target.name, metadata))
        return SimpleNamespace()

    monkeypatch.setattr(graph, "ensure_entity", fake_entity)
    monkeypatch.setattr(graph, "ensure_relation", fake_relation)
    tenant_id = uuid4()
    draft = SimpleNamespace(
        id=uuid4(), tenant_id=tenant_id, approval_status="approved", fact_type="product",
        payload={"name": "Follei Enterprise", "features": ["SAML"], "customer_segments": ["Enterprise sales"]},
        citation={"document_id": "doc-1", "document_name": "Pricing.pdf", "page": 2},
    )

    graph.sync_approved_fact_to_graph(object(), draft=draft)

    assert any(call[1:4] == ("Pricing.pdf", "defines", "Follei Enterprise") for call in relation_calls)
    assert any(call[1:4] == ("Follei Enterprise", "has_feature", "SAML") for call in relation_calls)
    assert any(call[1:4] == ("Follei Enterprise", "targets", "Enterprise sales") for call in relation_calls)
    assert all(call[4]["fact_draft_id"] == str(draft.id) for call in relation_calls)


def test_graph_rejects_unapproved_fact():
    draft = SimpleNamespace(approval_status="draft")
    with pytest.raises(ValueError, match="approved"):
        graph.sync_approved_fact_to_graph(object(), draft=draft)


def test_reviewed_relationships_create_feature_to_response_chain(monkeypatch):
    entities, relation_calls = {}, []

    def fake_entity(db, *, tenant_id, entity_type, name, metadata=None):
        key = (str(tenant_id), entity_type, name)
        return entities.setdefault(key, SimpleNamespace(id=uuid4(), name=name, entity_type=entity_type))

    def fake_relation(db, *, tenant_id, source, target, relation_type, metadata=None):
        relation_calls.append((source.entity_type, source.name, relation_type, target.entity_type, target.name))
        return SimpleNamespace()

    monkeypatch.setattr(graph, "ensure_entity", fake_entity)
    monkeypatch.setattr(graph, "ensure_relation", fake_relation)
    draft = SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), approval_status="approved", fact_type="product",
        citation={"document_name": "chain.txt"},
        payload={"name": "Follei", "relationships": [
            {"source_type": "feature", "source": "Grounded Context", "relation": "delivers_benefit", "target_type": "benefit", "target": "Accurate answers"},
            {"source_type": "benefit", "source": "Accurate answers", "relation": "serves_segment", "target_type": "customer_segment", "target": "SaaS teams"},
            {"source_type": "customer_segment", "source": "SaaS teams", "relation": "has_objection", "target_type": "objection", "target": "Migration complexity"},
            {"source_type": "objection", "source": "Migration complexity", "relation": "answered_by", "target_type": "response", "target": "Use phased onboarding"},
        ]},
    )

    graph.sync_approved_fact_to_graph(object(), draft=draft)

    assert relation_calls[-4:] == [
        ("feature", "Grounded Context", "delivers_benefit", "benefit", "Accurate answers"),
        ("benefit", "Accurate answers", "serves_segment", "customer_segment", "SaaS teams"),
        ("customer_segment", "SaaS teams", "has_objection", "objection", "Migration complexity"),
        ("objection", "Migration complexity", "answered_by", "response", "Use phased onboarding"),
    ]

