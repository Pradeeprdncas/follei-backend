from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.knowledge import conversation_memory
from app.services.rag.pipelines import chat as chat_pipeline_module


def test_rolling_summary_retains_prior_context_and_latest_turn():
    summary = conversation_memory._rolling_summary("Earlier need: Moodle integration.", "What is the enterprise price?", "The Enterprise plan supports SAML.")
    assert "Moodle integration" in summary
    assert "enterprise price" in summary
    assert "Enterprise plan" in summary


@pytest.mark.asyncio
async def test_chat_pipeline_persists_even_unsupported_turn(monkeypatch):
    persisted = {}

    async def no_context(*args, **kwargs):
        return "", []

    def persist(db, **kwargs):
        persisted.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(chat_pipeline_module, "retrieve_context", no_context)
    monkeypatch.setattr(chat_pipeline_module, "SessionLocal", lambda: SimpleNamespace(close=lambda: None, rollback=lambda: None))
    monkeypatch.setattr(chat_pipeline_module, "persist_chat_turn", persist)

    result = await chat_pipeline_module.chat_pipeline("Tell me the price", "7448b124-0844-451a-b4de-9275c0276d65")

    assert result["conversation_id"]
    assert persisted["question"] == "Tell me the price"
    assert persisted["supported"] is False
    assert persisted["citations"] == []


def test_invalid_tenant_cannot_create_durable_conversation():
    with pytest.raises(ValueError, match="tenant_id"):
        conversation_memory.resolve_conversation(object(), tenant_id="not-a-uuid", session_id=None, title="hello")

def test_turn_analysis_records_budget_competitor_intent_and_entities():
    sentiment, intent, entities = conversation_memory._turn_analysis("Our budget is tight and we compare Follei with Salesforce.")
    assert sentiment == "neutral"
    assert intent == "pricing"
    assert "Follei" in entities
    assert "Salesforce" in entities


def test_structured_summary_configuration_has_safe_interval():
    assert conversation_memory._settings.CONVERSATION_SUMMARY_TURN_INTERVAL >= 2
