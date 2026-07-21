"""Sales Executive worker regression: intent branching, proposal generation,
objection framing, and deal-stage progression side effects.

chat_pipeline() and the Lead Intelligence score are monkeypatched for
determinism; Lead/ConversationAction persistence runs against the real dev DB.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.agents.sales import worker as sales_worker
from app.services.agents.sales.intent import classify_sales_intent
from app.database.session import SessionLocal
from app.models.conversations.conversation import Conversation, ConversationAction
from app.models.leads.lead import Lead
from app.models.tenancy import Tenant


def test_classify_sales_intent():
    assert classify_sales_intent("Alright, let's do it and get started") == "closing"
    assert classify_sales_intent("Please send me a quote in writing") == "wants_proposal"
    assert classify_sales_intent("Honestly this seems too expensive") == "objection"
    assert classify_sales_intent("How does the API integration work?") == "product_discussion"


def _patch(monkeypatch, *, answer, scores=None):
    scores = scores or {"lead_score": 65.0, "qualification_score": 60.0, "conversion_probability": 0.65}
    async def fake_chat_pipeline(**kwargs):
        return {"answer": answer, "citations": [], "confidence": 0.8, "supported": True,
                "reason": "ok", "conflicts": [], "conversation_id": kwargs.get("session_id")}
    monkeypatch.setattr(sales_worker, "chat_pipeline", fake_chat_pipeline)
    monkeypatch.setattr(sales_worker.LeadScoringService, "score", classmethod(lambda cls, text, **kw: scores))


def _seed(db, *, status="qualified"):
    tenant_id, lead_id, conv_id = uuid4(), uuid4(), uuid4()
    db.add(Tenant(id=tenant_id, name=f"Sales test {tenant_id}"))
    db.commit()
    db.add(Lead(id=lead_id, tenant_id=tenant_id, email=f"{lead_id}@example.com", status=status, current_temperature="warm", current_score=50.0, company="Acme"))
    db.add(Conversation(id=conv_id, tenant_id=tenant_id, lead_id=lead_id, channel="voice", status="active"))
    db.commit()
    return tenant_id, lead_id, conv_id


@pytest.mark.asyncio
async def test_objection_is_framed_with_reassurance(monkeypatch):
    db = SessionLocal()
    try:
        tenant_id, lead_id, conv_id = _seed(db)
        _patch(monkeypatch, answer="Our ROI typically pays back in 4 months.")
        result = await sales_worker.handle_sales_turn(
            db, tenant_id=str(tenant_id), text="This is too expensive for us right now",
            lead_id=str(lead_id), session_id=str(conv_id),
        )
        assert result["intent"] == "objection"
        assert result["reply"].startswith(sales_worker.OBJECTION_PREFIX)
        assert "ROI typically pays back" in result["reply"]
        assert result["actions"] == []
    finally:
        db.query(Tenant).filter(Tenant.name.like("Sales test %")).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_proposal_request_generates_and_records_proposal(monkeypatch):
    db = SessionLocal()
    try:
        tenant_id, lead_id, conv_id = _seed(db)
        _patch(monkeypatch, answer="Here's how the enterprise tier is structured.")
        result = await sales_worker.handle_sales_turn(
            db, tenant_id=str(tenant_id), text="Can you put together a proposal for us?",
            lead_id=str(lead_id), session_id=str(conv_id),
        )
        assert result["intent"] == "wants_proposal"
        assert "proposal_generated" in result["actions"]
        assert result["proposal"]["company"] == "Acme"
        assert result["reply"] == sales_worker.PROPOSAL_ACK

        db.expire_all()
        action = db.query(ConversationAction).filter(
            ConversationAction.conversation_id == conv_id,
            ConversationAction.action_type == "proposal_generated",
        ).one()
        assert action.payload["lead_id"] == str(lead_id)
        assert db.query(Lead).filter(Lead.id == lead_id).one().status == "proposal"
    finally:
        db.query(Tenant).filter(Tenant.name.like("Sales test %")).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_closing_signal_marks_deal_won(monkeypatch):
    db = SessionLocal()
    try:
        tenant_id, lead_id, conv_id = _seed(db)
        _patch(monkeypatch, answer="Fantastic.")
        result = await sales_worker.handle_sales_turn(
            db, tenant_id=str(tenant_id), text="Great, let's move forward — where do I sign?",
            lead_id=str(lead_id), session_id=str(conv_id),
        )
        assert result["intent"] == "closing"
        assert result["deal_stage"] == "closed_won"
        assert "deal_stage_change" in result["actions"]
        assert result["reply"] == sales_worker.CLOSING_ACK

        db.expire_all()
        lead = db.query(Lead).filter(Lead.id == lead_id).one()
        assert lead.status == "converted"
        assert lead.current_temperature == "customer"
        action = db.query(ConversationAction).filter(
            ConversationAction.conversation_id == conv_id,
            ConversationAction.action_type == "deal_stage_change",
        ).one()
        assert action.payload["stage"] == "closed_won"
    finally:
        db.query(Tenant).filter(Tenant.name.like("Sales test %")).delete(synchronize_session=False)
        db.commit()
        db.close()
