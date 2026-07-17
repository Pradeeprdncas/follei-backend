import pytest

from app.services.knowledge import orchestrator


@pytest.mark.asyncio
async def test_orchestrator_ranks_sources_by_trust_and_freshness_and_flags_approved_conflict(monkeypatch):
    old = orchestrator._decorate(
        {"fact_id": "old-price", "fact_type": "pricing", "topic": "Enterprise", "value": [{"price": "$99"}], "approved": True, "citation": {"document": "pricing-2024.pdf"}},
        source="postgres", updated_at="2024-01-01T00:00:00+00:00",
    )
    fresh = orchestrator._decorate(
        {"fact_id": "new-price", "fact_type": "pricing", "topic": "Enterprise", "value": [{"price": "$129"}], "approved": True, "citation": {"document": "pricing-2026.pdf"}},
        source="postgres", updated_at="2026-07-01T00:00:00+00:00",
    )
    captured = {}

    def postgres_context(db, tenant_id, lead_id):
        captured["tenant_id"] = tenant_id
        return {"tenant_id": tenant_id, "approved": [old, fresh]}, []

    async def evidence(query, tenant_id, top_k):
        captured["evidence_tenant"] = tenant_id
        return [{"chunk_id": "chunk-1", "text": "Enterprise price", "updated_at": "2026-06-01T00:00:00+00:00", "score": 0.9}]

    monkeypatch.setattr(orchestrator, "load_postgres_context", postgres_context)
    monkeypatch.setattr(orchestrator, "retrieve_dense", evidence)
    monkeypatch.setattr(orchestrator, "traverse_graph", lambda db, tenant_id, query: [{"from": "Enterprise", "relation": "defines", "to": "Plan"}])
    monkeypatch.setattr(orchestrator, "get_context", lambda **kwargs: {"updated_at": "2026-07-10T00:00:00+00:00", "competitors": [{"value": "Salesforce"}]})

    result = await orchestrator.build_agent_context(db=object(), tenant_id="tenant-a", query="What is the Enterprise price?", lead_id="lead-a")

    assert captured == {"tenant_id": "tenant-a", "evidence_tenant": "tenant-a"}
    assert result["trust_policy"] == {"postgres": 1, "graph": 2, "qdrant": 3, "ferret": 4}
    assert result["facts"]["approved"][0]["fact_id"] == "new-price"
    assert result["facts"]["approved"][0]["freshness_score"] > result["facts"]["approved"][1]["freshness_score"]
    assert result["relationships"][0]["source"] == "graph"
    assert result["evidence"][0]["trust_rank"] == 3
    assert result["customer_context"]["trust_rank"] == 4
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["requires_review"] is True
    assert [candidate["fact_id"] for candidate in result["conflicts"][0]["candidates"]] == ["new-price", "old-price"]