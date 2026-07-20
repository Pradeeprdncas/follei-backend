import pytest
from app.services.rag.retrieval.approval import approved_filter, requires_approval
from app.services.knowledge import orchestrator


def test_approval_policy_requires_approved_for_pricing_policy_plan_faq():
    assert requires_approval("What is the enterprise price?")
    assert requires_approval("Explain the security policy")
    assert requires_approval("Which plan includes SAML?")
    assert requires_approval("How does onboarding work?", category="faq")
    query_filter = approved_filter("tenant-a", require_approved=True)
    assert {item["key"] for item in query_filter["must"]} == {"tenant_id", "approval_status"}
    assert {item["key"] for item in approved_filter("tenant-a", require_approved=False)["must"]} == {"tenant_id", "approval_status"}


@pytest.mark.asyncio
async def test_orchestrator_merges_all_four_sources_in_fixed_order(monkeypatch):
    calls = []
    monkeypatch.setattr(orchestrator, "load_postgres_context", lambda db, tenant_id, lead_id, query: ({"tenant_id": tenant_id, "lead": {"status": "qualified"}}, [{"from": "lead-1", "relation": "needs", "to": "Moodle"}]))
    async def fake_retrieve(query, tenant_id, top_k=5):
        calls.append("qdrant")
        return [{"chunk_id": "chunk-1", "document_id": "doc-1", "page": 4, "heading_path": ["Pricing", "Enterprise"], "approval_status": "approved", "text": "Moodle integration", "source_type": "pdf"}]
    monkeypatch.setattr(orchestrator, "retrieve_dense", fake_retrieve)
    def fake_context(**kwargs):
        calls.append("ferretdb")
        return {"requirements": ["Moodle integration"], "objections": ["security"]}
    monkeypatch.setattr(orchestrator, "get_context", fake_context)
    result = await orchestrator.build_agent_context(db=object(), tenant_id="tenant-a", query="pricing for Moodle", lead_id="lead-1")
    assert result["facts"]["lead"]["status"] == "qualified"
    assert result["relationships"][0]["to"] == "Moodle"
    assert result["evidence"][0]["approval_status"] == "approved"
    assert result["customer_context"]["requirements"] == ["Moodle integration"]
    assert result["citations"][0]["heading_path"] == ["Pricing", "Enterprise"]
    assert calls == ["qdrant", "ferretdb"]
