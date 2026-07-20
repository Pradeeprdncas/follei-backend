import pytest

from app.services.rag.retrieval.rerank import rerank


@pytest.mark.asyncio
async def test_strong_direct_match_prunes_unrelated_semantic_candidates():
    results = [
        {"chunk_id": "weak-1", "text": "Customer segments and sales data"},
        {"chunk_id": "exact", "text": "Knowledge Recovery Runbook: PostgreSQL, Qdrant, and FerretDB data stores"},
        {"chunk_id": "weak-2", "text": "General knowledge article for support"},
    ]

    ranked = await rerank(
        "According to the Knowledge Recovery Runbook, what do the three data stores contain?",
        results,
        top_k=5,
    )

    assert [item["chunk_id"] for item in ranked] == ["exact"]


@pytest.mark.asyncio
async def test_weak_lexical_signal_preserves_semantic_candidates_and_order():
    results = [
        {"chunk_id": "semantic-first", "text": "Return merchandise within six weeks"},
        {"chunk_id": "incidental", "text": "A customer asked how support works"},
    ]

    ranked = await rerank("How long can a buyer send an item back?", results, top_k=5)

    assert [item["chunk_id"] for item in ranked] == ["semantic-first", "incidental"]
