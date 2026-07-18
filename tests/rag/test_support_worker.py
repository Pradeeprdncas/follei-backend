"""Support worker regression: grounded replies vs. escalation, reusing
chat_pipeline (which already calls the orchestrator per Fix 2) rather than
duplicating a second orchestrator call.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agents.support import worker as worker_module
from app.services.agents.support.intent import classify_intent


def test_classify_intent_detects_explicit_human_request():
    assert classify_intent("Can I speak to a human please?") == "escalation_requested"
    assert classify_intent("I want to talk to an agent") == "escalation_requested"


def test_classify_intent_detects_complaint():
    assert classify_intent("This is broken and I am furious") == "complaint"


def test_classify_intent_defaults_to_question():
    assert classify_intent("What is your refund window?") == "question"


class _FakeDB:
    def __init__(self):
        self.conversations = {}

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self._match

    def commit(self):
        pass


def _fake_db_with_conversation(conversation):
    db = _FakeDB()
    db._match = conversation
    return db


@pytest.mark.asyncio
async def test_explicit_human_request_skips_retrieval_and_escalates(monkeypatch):
    chat_pipeline_mock = AsyncMock(side_effect=AssertionError("chat_pipeline should not be called for an explicit human request"))
    monkeypatch.setattr(worker_module, "chat_pipeline", chat_pipeline_mock)

    conversation = SimpleNamespace(id="conv-1", status="open", metadata_={})

    def fake_persist_chat_turn(db, **kwargs):
        assert kwargs["answer"] == worker_module.ESCALATION_ACK
        assert kwargs["confidence"] == 0.0
        return conversation

    monkeypatch.setattr(worker_module, "persist_chat_turn", fake_persist_chat_turn)
    db = _fake_db_with_conversation(conversation)

    result = await worker_module.handle_inbound_message(db, tenant_id="tenant-a", text="I need to speak to a human agent now")

    chat_pipeline_mock.assert_not_called()
    assert result["escalated"] is True
    assert result["escalation_reason"] == "explicit_human_request"
    assert result["reply"] == worker_module.ESCALATION_ACK
    assert conversation.status == "needs_human"


@pytest.mark.asyncio
async def test_grounded_question_returns_the_chat_pipeline_answer(monkeypatch):
    async def fake_chat_pipeline(**_kwargs):
        return {"answer": "The refund window is 45 days.", "citations": [{"chunk_id": "c1"}], "confidence": 0.9, "supported": True, "reason": "ok", "conflicts": [], "conversation_id": "conv-2"}

    monkeypatch.setattr(worker_module, "chat_pipeline", fake_chat_pipeline)
    db = _fake_db_with_conversation(SimpleNamespace(id="conv-2", status="open", metadata_={}))

    result = await worker_module.handle_inbound_message(db, tenant_id="tenant-a", text="What is the refund window?")

    assert result["escalated"] is False
    assert result["reply"] == "The refund window is 45 days."
    assert result["conversation_id"] == "conv-2"


@pytest.mark.asyncio
async def test_conflicts_trigger_escalation_instead_of_answering(monkeypatch):
    conflict = {"type": "approved_fact_conflict", "requires_review": True}

    async def fake_chat_pipeline(**_kwargs):
        return {"answer": "should not be sent to the customer", "citations": [], "confidence": 0.0, "supported": False, "reason": "conflict", "conflicts": [conflict], "conversation_id": "conv-3"}

    monkeypatch.setattr(worker_module, "chat_pipeline", fake_chat_pipeline)
    conversation = SimpleNamespace(id="conv-3", status="open", metadata_={})
    db = _fake_db_with_conversation(conversation)

    result = await worker_module.handle_inbound_message(db, tenant_id="tenant-a", text="What does the enterprise plan cost?")

    assert result["escalated"] is True
    assert result["escalation_reason"] == "conflicting_approved_facts"
    assert result["reply"] == worker_module.ESCALATION_ACK
    assert "should not be sent" not in result["reply"]
    assert conversation.status == "needs_human"
    assert conversation.metadata_["escalation"]["reason"] == "conflicting_approved_facts"


@pytest.mark.asyncio
async def test_low_confidence_triggers_escalation(monkeypatch):
    async def fake_chat_pipeline(**_kwargs):
        return {"answer": "maybe this is right", "citations": [], "confidence": 0.2, "supported": True, "reason": "weak", "conflicts": [], "conversation_id": "conv-4"}

    monkeypatch.setattr(worker_module, "chat_pipeline", fake_chat_pipeline)
    conversation = SimpleNamespace(id="conv-4", status="open", metadata_={})
    db = _fake_db_with_conversation(conversation)

    result = await worker_module.handle_inbound_message(db, tenant_id="tenant-a", text="Do you support SSO?")

    assert result["escalated"] is True
    assert result["escalation_reason"] == "low_confidence"
