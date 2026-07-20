import pytest

from app.services.agents import orchestrator as worker_orchestrator


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_type", [
    "support", "sdr", "sales", "customer_success", "collections",
    "account_manager", "executive", "general",
])
async def test_every_worker_uses_the_same_validated_agent_context(monkeypatch, worker_type):
    called = {}

    async def fake_context(**kwargs):
        called.update(kwargs)
        return {
            "facts": {"approved": [{"source": "postgres"}]},
            "relationships": [{"source": "graph"}],
            "evidence": [{"source": "qdrant"}],
            "customer_context": {"source": "ferret"},
            "citations": [],
            "conflicts": [],
            "trust_policy": {"postgres": 1, "graph": 2, "qdrant": 3, "ferret": 4},
        }

    monkeypatch.setattr(worker_orchestrator, "build_agent_context", fake_context)

    result = await worker_orchestrator.build_worker_context(
        db=object(), worker_type=worker_type, tenant_id="tenant-a", query="Enterprise price"
    )

    assert called["tenant_id"] == "tenant-a"
    assert result["facts"]["approved"][0]["source"] == "postgres"
    assert result["relationships"][0]["source"] == "graph"
    assert result["evidence"][0]["source"] == "qdrant"
    assert result["customer_context"]["source"] == "ferret"


@pytest.mark.asyncio
async def test_unknown_worker_type_is_rejected():
    with pytest.raises(ValueError, match="Unknown worker type"):
        await worker_orchestrator.build_worker_context(
            db=object(), worker_type="unscoped-worker", tenant_id="tenant-a", query="price"
        )
