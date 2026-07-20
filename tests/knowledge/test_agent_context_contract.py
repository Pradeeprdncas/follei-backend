from app.services.knowledge.contracts import AgentContextContract
from app.services.knowledge.orchestrator import _query_matches


def test_worker_context_contract_carries_all_four_layers_and_conflicts():
    value = AgentContextContract.model_validate({"facts": {"approved": [{"source": "postgres"}]}, "relationships": [{"source": "graph"}], "evidence": [{"source": "qdrant"}], "customer_context": {"source": "ferret"}, "citations": [], "conflicts": [{"requires_review": True}], "trust_policy": {"postgres": 1, "graph": 2, "qdrant": 3, "ferret": 4}})
    assert value.facts["approved"][0]["source"] == "postgres"
    assert {value.relationships[0]["source"], value.evidence[0]["source"], value.customer_context["source"]} == {"graph", "qdrant", "ferret"}
    assert value.conflicts[0]["requires_review"] is True


def test_query_relevance_ignores_question_stopwords():
    assert _query_matches("What is the Enterprise price?", "Enterprise", [{"price": 999}], "pricing")
    assert not _query_matches("What is the Enterprise price?", "Refund Policy", "45 days from purchase", "policy")
    assert not _query_matches("What is the Enterprise price?", "How long is the refund window?", "45 days", "faq")
    assert not _query_matches(
        "According to the Knowledge Recovery Runbook, what do the three data stores contain?",
        "Follei Knowledge System", "Grounded worker context", "product",
    )
