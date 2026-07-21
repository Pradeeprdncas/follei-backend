"""SDR worker regression: intent branching, lead qualification side effects,
meeting-booking action, and the Sales handoff flag.

chat_pipeline() and the Lead Intelligence score are monkeypatched for
determinism (this exercises the worker's branching, not the scorer's
heuristics); Lead/ConversationAction persistence runs against the real dev DB,
matching this repo's SessionLocal-based test convention.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.agents.sdr import worker as sdr_worker
from app.services.agents.sdr.intent import classify_sdr_intent
from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation, ConversationAction
from app.models.leads.lead import Lead
from app.models.tenancy import Tenant


def test_classify_sdr_intent():
    assert classify_sdr_intent("Can we book a meeting next week?") == "wants_meeting"
    assert classify_sdr_intent("what's the pricing for enterprise?") == "asking_about_pricing"
    assert classify_sdr_intent("tell me more about what you do") == "general_discovery"


def _patch_pipeline_and_scores(monkeypatch, *, answer, scores):
    async def fake_chat_pipeline(**kwargs):
        return {"answer": answer, "citations": [], "confidence": 0.8, "supported": True,
                "reason": "ok", "conflicts": [], "conversation_id": kwargs.get("session_id")}
    monkeypatch.setattr(sdr_worker, "chat_pipeline", fake_chat_pipeline)
    monkeypatch.setattr(sdr_worker.LeadScoringService, "score", classmethod(lambda cls, text, **kw: scores))


def _seed(db):
    tenant_id, lead_id, conv_id = uuid4(), uuid4(), uuid4()
    db.add(Tenant(id=tenant_id, name=f"SDR test {tenant_id}"))
    db.commit()
    db.add(Lead(id=lead_id, tenant_id=tenant_id, email=f"{lead_id}@example.com", status="new", current_temperature="cold", current_score=0.0))
    db.add(Conversation(id=conv_id, tenant_id=tenant_id, lead_id=lead_id, channel="voice", status="active"))
    db.commit()
    return tenant_id, lead_id, conv_id


@pytest.mark.asyncio
async def test_meeting_request_records_action_and_acknowledges(monkeypatch):
    db = SessionLocal()
    try:
        tenant_id, lead_id, conv_id = _seed(db)
        _patch_pipeline_and_scores(
            monkeypatch, answer="Sure, happy to help.",
            scores={"lead_score": 30.0, "qualification_score": 20.0, "icp_score": 40.0,
                    "intent_score": 50.0, "engagement_score": 30.0, "buying_signal_score": 20.0,
                    "relationship_score": 25.0, "conversion_probability": 0.3},
        )
        result = await sdr_worker.handle_sdr_turn(
            db, tenant_id=str(tenant_id), text="Can we schedule a demo?",
            lead_id=str(lead_id), session_id=str(conv_id), channel="voice",
        )
        assert result["intent"] == "wants_meeting"
        assert "meeting_booked" in result["actions"]
        assert result["reply"] == sdr_worker.MEETING_ACK
        assert result["handoff_to_sales"] is False  # lead_score 30 < 40 threshold

        db.expire_all()
        action = db.query(ConversationAction).filter(
            ConversationAction.conversation_id == conv_id,
            ConversationAction.action_type == "meeting_booked",
        ).one()
        assert action.payload["lead_id"] == str(lead_id)
    finally:
        db.query(Tenant).filter(Tenant.name.like("SDR test %")).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_high_score_flags_handoff_and_qualifies_lead(monkeypatch):
    db = SessionLocal()
    try:
        tenant_id, lead_id, conv_id = _seed(db)
        _patch_pipeline_and_scores(
            monkeypatch, answer="Our platform automates that.",
            scores={"lead_score": 82.0, "qualification_score": 75.0, "icp_score": 80.0,
                    "intent_score": 85.0, "engagement_score": 70.0, "buying_signal_score": 78.0,
                    "relationship_score": 60.0, "conversion_probability": 0.82},
        )
        result = await sdr_worker.handle_sdr_turn(
            db, tenant_id=str(tenant_id), text="We're evaluating vendors now, tell me about automation",
            lead_id=str(lead_id), session_id=str(conv_id), channel="voice",
        )
        assert result["intent"] == "general_discovery"
        assert result["handoff_to_sales"] is True
        assert result["qualification"]["qualified"] is True
        # Discovery reply pairs the grounded answer with a next-action nudge.
        assert "Our platform automates that." in result["reply"]

        db.expire_all()
        lead = db.query(Lead).filter(Lead.id == lead_id).one()
        assert lead.status == "qualified"
        assert lead.current_temperature == "hot"
        assert lead.current_score == 82.0
    finally:
        db.query(Tenant).filter(Tenant.name.like("SDR test %")).delete(synchronize_session=False)
        db.commit()
        db.close()
