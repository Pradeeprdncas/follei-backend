from types import SimpleNamespace

import pytest

from app.services.rag.pipelines import retrieval


@pytest.mark.asyncio
async def test_retrieve_context_compresses_chunk_objects_before_formatting(monkeypatch):
    chunks = [
        SimpleNamespace(id="chunk-1", text="Enterprise plan includes SAML."),
        SimpleNamespace(id="chunk-2", text="Pricing is annual."),
    ]
    captured = {}

    async def fake_hybrid(*_args, **_kwargs):
        return [{"chunk_id": "chunk-1"}, {"chunk_id": "chunk-2"}]

    class Repository:
        def __init__(self, _db):
            pass

        def get_by_ids(self, ids):
            assert ids == ["chunk-1", "chunk-2"]
            return chunks

    def fake_compress(values, max_tokens):
        captured["values"] = values
        captured["max_tokens"] = max_tokens
        return [chunks[0]]

    monkeypatch.setattr(retrieval, "hybrid_retrieve", fake_hybrid)
    monkeypatch.setattr(retrieval, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(retrieval, "ChunkRepository", Repository)
    monkeypatch.setattr(retrieval, "compress_context", fake_compress)
    monkeypatch.setattr(retrieval, "build_context", lambda ids: f"DOCUMENT CONTENT: {ids[0]}")

    context, chunk_ids = await retrieval.retrieve_context("What is included?", "tenant-a")

    assert captured["values"] == chunks
    assert all(hasattr(chunk, "text") for chunk in captured["values"])
    assert context == "DOCUMENT CONTENT: chunk-1"
    assert chunk_ids == ["chunk-1"]