"""LeadScoringWorker regression: EVENT_CONVERSATION_ANALYSIS_COMPLETED -> a
LeadScore row + Lead.current_score/current_temperature, against the real dev
database (matching this repo's existing SessionLocal-based test convention —
see tests/knowledge/test_fact_approval_store_consistency.py).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation
from app.models.leads.lead import Lead
from app.models.leads.lead_score import LeadScore
from app.models.tenancy import Tenant
from app.workers.lead_scoring_worker import LeadScoringWorker


def _make_message(event_type: str, data: dict):
    return SimpleNamespace(value=json.dumps({"event_type": event_type, "data": data}), key=event_type)


def test_process_ignores_events_of_a_different_type(monkeypatch):
    worker = LeadScoringWorker()
    called = []
    monkeypatch.setattr(worker, "_persist", lambda *a, **k: called.append((a, k)))

    worker._process(_make_message("some.other.event", {"conversation_id": "x", "lead_score": {"lead_score": 80}}))

    assert called == []


def test_process_ignores_events_without_a_lead_score_payload(monkeypatch):
    worker = LeadScoringWorker()
    called = []
    monkeypatch.setattr(worker, "_persist", lambda *a, **k: called.append((a, k)))

    worker._process(_make_message("conversation.analysis.completed", {"conversation_id": "x"}))

    assert called == []


def test_process_routes_a_matching_event_to_persist(monkeypatch):
    worker = LeadScoringWorker()
    calls = []
    monkeypatch.setattr(worker, "_persist", lambda tenant_id, conversation_id, payload: calls.append((tenant_id, conversation_id, payload)))

    worker._process(_make_message("conversation.analysis.completed", {
        "tenant_id": "t1", "conversation_id": "c1", "lead_score": {"lead_score": 80},
    }))

    assert calls == [("t1", "c1", {"lead_score": 80})]


def test_persist_writes_lead_score_and_updates_lead_temperature():
    tenant_id, lead_id, conversation_id = uuid4(), uuid4(), uuid4()
    db = SessionLocal()
    worker = LeadScoringWorker()
    try:
        tenant = Tenant(id=tenant_id, name=f"Lead scoring worker test {tenant_id}")
        db.add(tenant)
        db.commit()

        lead = Lead(id=lead_id, tenant_id=tenant_id, email="lead@example.com", current_score=10.0, current_temperature="cold")
        db.add(lead)
        db.commit()

        conversation = Conversation(id=conversation_id, tenant_id=tenant_id, lead_id=lead_id, channel="voice", status="active")
        db.add(conversation)
        db.commit()

        worker._persist(str(tenant_id), str(conversation_id), {
            "icp_score": 80.0, "intent_score": 85.0, "engagement_score": 70.0,
            "qualification_score": 90.0, "buying_signal_score": 75.0, "relationship_score": 60.0,
            "lead_score": 83.0, "lead_category": "Hot Lead",
            "bant": {"budget": 0.8, "authority": 0.7, "need": 0.9, "timeline": 0.6},
            "confidence": 0.9,
        })

        db.expire_all()
        refreshed_lead = db.query(Lead).filter(Lead.id == lead_id).one()
        score_row = db.query(LeadScore).filter(LeadScore.lead_id == lead_id).one()

        assert refreshed_lead.current_score == 83.0
        assert refreshed_lead.current_temperature == "hot"
        assert refreshed_lead.analysis_confidence == 0.9
        assert score_row.score == 83
        assert score_row.previous_score == 10
        assert score_row.score_delta == 73
        assert score_row.event_type == "conversation_analysis"
        assert score_row.event_metadata["bant"]["budget"] == 0.8
    finally:
        db.query(Tenant).filter(Tenant.id == tenant_id).delete()
        db.commit()
        db.close()


def test_persist_skips_conversation_without_a_linked_lead():
    tenant_id, conversation_id = uuid4(), uuid4()
    db = SessionLocal()
    worker = LeadScoringWorker()
    try:
        tenant = Tenant(id=tenant_id, name=f"Lead scoring worker unlinked test {tenant_id}")
        db.add(tenant)
        db.commit()

        conversation = Conversation(id=conversation_id, tenant_id=tenant_id, lead_id=None, channel="voice", status="active")
        db.add(conversation)
        db.commit()

        # Should not raise even though there is no lead to score.
        worker._persist(str(tenant_id), str(conversation_id), {"lead_score": 50.0})

        assert db.query(LeadScore).filter(LeadScore.tenant_id == tenant_id).count() == 0
    finally:
        db.query(Tenant).filter(Tenant.id == tenant_id).delete()
        db.commit()
        db.close()
