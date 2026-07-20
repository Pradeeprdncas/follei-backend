"""Fix 2 regression: chat_pipeline() must call the knowledge orchestrator and
must never silently pick a side when approved facts conflict."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.rag.pipelines import chat as chat_module


def test_retrieval_observability_payload_serializes_uuid_citations():
    citation_id = uuid4()

    safe = chat_module._json_safe([{"citation": {"fact_id": citation_id}}])

    assert safe == [{"citation": {"fact_id": str(citation_id)}}]


class _FakeDB:
    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture(autouse=True)
def _common_mocks(monkeypatch):
    monkeypatch.setattr(chat_module, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(chat_module, "optimize_user_request", AsyncMock(return_value={}))

    def fake_persist(*_args, **_kwargs):
        return SimpleNamespace(id="conv-1")

    monkeypatch.setattr(chat_module, "persist_chat_turn", fake_persist)
    monkeypatch.setattr(chat_module, "summarize_conversation", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_module, "extract_citations", lambda ids: [{"chunk_id": i} for i in ids])


async def _fake_retrieve_context(*_a, **_k):
    return "Some retrieved chunk text about refunds.", ["chunk-1"]


def test_chat_pipeline_calls_build_agent_context(monkeypatch):
    called = {}

    async def fake_build_agent_context(*, db, tenant_id, query, **_kwargs):
        called["tenant_id"] = tenant_id
        called["query"] = query
        return {"facts": {"approved": []}, "relationships": [], "customer_context": {}, "conflicts": []}

    monkeypatch.setattr(chat_module, "retrieve_context", _fake_retrieve_context)
    monkeypatch.setattr(chat_module, "build_agent_context", fake_build_agent_context)
    monkeypatch.setattr(chat_module, "generate_answer", AsyncMock(return_value="The refund window is 45 days."))

    import asyncio
    result = asyncio.run(chat_module.chat_pipeline("What is the refund window?", "tenant-a"))

    assert called.get("tenant_id") == "tenant-a"
    assert called.get("query") == "What is the refund window?"
    assert result["answer"] == "The refund window is 45 days."
    assert result["conflicts"] == []


def test_chat_pipeline_includes_approved_fact_in_context_and_citations(monkeypatch):
    captured_context = {}

    async def fake_build_agent_context(*, db, tenant_id, query, **_kwargs):
        return {
            "facts": {"approved": [{
                "fact_id": "fact-123", "fact_type": "pricing", "topic": "enterprise plan",
                "value": "$500/mo", "citation": {"document_id": "doc-9"},
            }]},
            "relationships": [], "customer_context": {}, "conflicts": [],
        }

    async def fake_generate_answer(question, context, system_prompt):
        captured_context["context"] = context
        return "Enterprise plan is $500/mo."

    monkeypatch.setattr(chat_module, "retrieve_context", _fake_retrieve_context)
    monkeypatch.setattr(chat_module, "build_agent_context", fake_build_agent_context)
    monkeypatch.setattr(chat_module, "generate_answer", fake_generate_answer)

    import asyncio
    result = asyncio.run(chat_module.chat_pipeline("What does the enterprise plan cost?", "tenant-a"))

    assert "$500/mo" in captured_context["context"]
    assert "enterprise plan" in captured_context["context"]
    fact_citations = [c for c in result["citations"] if c.get("source") == "postgres_fact"]
    assert len(fact_citations) == 1
    assert fact_citations[0]["fact_id"] == "fact-123"
    assert fact_citations[0]["citation"] == {"document_id": "doc-9"}


def test_chat_pipeline_emits_graph_and_memory_provenance(monkeypatch):
    async def context(**_kwargs):
        return {"facts": {"approved": []}, "relationships": [{"source": "graph", "from": "Enterprise", "relation": "includes", "to": "Support", "citation": {"document_id": "doc-g"}, "trust_rank": 2}], "customer_context": {"source": "ferret", "subject_type": "tenant", "subject_id": "tenant-a", "trust_rank": 4}, "memory_evidence": [{"source": "ferret", "document_id": "doc-m", "title": "Support guide", "summary": "Support details", "projection_type": "indexed_document_summary", "trust_rank": 4}], "conflicts": []}
    monkeypatch.setattr(chat_module, "retrieve_context", _fake_retrieve_context)
    monkeypatch.setattr(chat_module, "build_agent_context", context)
    monkeypatch.setattr(chat_module, "generate_answer", AsyncMock(return_value="Enterprise includes Support."))
    import asyncio
    result = asyncio.run(chat_module.chat_pipeline("What is included?", "tenant-a"))
    assert any(item["source"] == "graph_relation" for item in result["citations"])
    assert any(item["source"] == "ferretdb_memory" for item in result["citations"])
    assert any(item["source"] == "ferretdb_document_memory" and item["document_id"] == "doc-m" for item in result["citations"])


def test_chat_pipeline_does_not_silently_pick_a_side_on_conflict(monkeypatch):
    conflict = {
        "type": "approved_fact_conflict", "fact_type": "pricing", "topic": "enterprise plan",
        "requires_review": True, "reason": "disagree",
        "candidates": [{"fact_id": "fact-1", "value": "$500/mo"}, {"fact_id": "fact-2", "value": "$700/mo"}],
    }

    async def fake_build_agent_context(*, db, tenant_id, query, **_kwargs):
        return {
            "facts": {"approved": [
                {"fact_id": "fact-1", "fact_type": "pricing", "topic": "enterprise plan", "value": "$500/mo", "citation": {}},
                {"fact_id": "fact-2", "fact_type": "pricing", "topic": "enterprise plan", "value": "$700/mo", "citation": {}},
            ]},
            "relationships": [], "customer_context": {}, "conflicts": [conflict],
        }

    generate_answer_mock = AsyncMock(return_value="should never be called")
    monkeypatch.setattr(chat_module, "retrieve_context", _fake_retrieve_context)
    monkeypatch.setattr(chat_module, "build_agent_context", fake_build_agent_context)
    monkeypatch.setattr(chat_module, "generate_answer", generate_answer_mock)

    import asyncio
    result = asyncio.run(chat_module.chat_pipeline("What does the enterprise plan cost?", "tenant-a"))

    generate_answer_mock.assert_not_called()
    assert result["conflicts"] == [conflict]
    assert result["supported"] is False
    assert "$500/mo" not in result["answer"]
    assert "$700/mo" not in result["answer"]
    assert "review" in result["reason"].lower()


def test_chat_pipeline_survives_orchestrator_failure(monkeypatch):
    async def failing_build_agent_context(*_a, **_k):
        raise RuntimeError("orchestrator db unavailable")

    monkeypatch.setattr(chat_module, "retrieve_context", _fake_retrieve_context)
    monkeypatch.setattr(chat_module, "build_agent_context", failing_build_agent_context)
    monkeypatch.setattr(chat_module, "generate_answer", AsyncMock(return_value="fallback answer"))

    import asyncio
    result = asyncio.run(chat_module.chat_pipeline("What is the refund window?", "tenant-a"))

    assert result["answer"] == "fallback answer"
    assert result["conflicts"] == []
