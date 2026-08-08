from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.knowledge.outbox import deliver_event
from app.services.knowledge import outbox


def _event():
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        aggregate_id=uuid4(),
        event_type="conversation.summary.ready",
        deliveries={"postgres": "completed", "ferret": "pending", "qdrant": "pending"},
        status="pending",
        attempt_count=0,
        last_error=None,
        completed_at=None,
    )


@pytest.mark.asyncio
async def test_retry_after_mid_delivery_crash_skips_completed_target_and_finishes_once():
    event = _event()
    calls = {"ferret": 0, "qdrant": 0, "checkpoints": 0}

    async def ferret(_event):
        calls["ferret"] += 1
        return "completed"

    async def qdrant(_event):
        calls["qdrant"] += 1
        return "completed"

    def crash_after_ferret_checkpoint():
        calls["checkpoints"] += 1
        # The first checkpoint marks the event processing; the second is after
        # FerretDB completed, which simulates a process termination at that point.
        if calls["checkpoints"] == 2:
            raise KeyboardInterrupt("simulated process stop")

    with pytest.raises(KeyboardInterrupt):
        await deliver_event(event, handlers={"ferret": ferret, "qdrant": qdrant}, checkpoint=crash_after_ferret_checkpoint)

    assert event.deliveries == {"postgres": "completed", "ferret": "completed", "qdrant": "pending"}
    assert calls == {"ferret": 1, "qdrant": 0, "checkpoints": 2}

    completed = await deliver_event(event, handlers={"ferret": ferret, "qdrant": qdrant})

    assert completed.status == "completed"
    assert completed.deliveries == {"postgres": "completed", "ferret": "completed", "qdrant": "completed"}
    assert calls["ferret"] == 1
    assert calls["qdrant"] == 1


@pytest.mark.asyncio
async def test_failed_target_is_retryable_without_repeating_completed_target():
    event = _event()
    calls = {"ferret": 0, "qdrant": 0}

    async def ferret(_event):
        calls["ferret"] += 1
        return "completed"

    async def qdrant_fails(_event):
        calls["qdrant"] += 1
        raise RuntimeError("temporary Qdrant outage")

    first = await deliver_event(event, handlers={"ferret": ferret, "qdrant": qdrant_fails})
    assert first.status == "retrying"
    assert first.deliveries["ferret"] == "completed"
    assert first.deliveries["qdrant"] == "failed"

    async def qdrant_recovers(_event):
        calls["qdrant"] += 1
        return "completed"

    second = await deliver_event(event, handlers={"ferret": ferret, "qdrant": qdrant_recovers})
    assert second.status == "completed"
    assert calls == {"ferret": 1, "qdrant": 2}


@pytest.mark.asyncio
async def test_document_indexed_routes_document_and_structural_chunks_to_ferret(monkeypatch):
    captured = {"document": {}, "chunks": {}}

    def write_projection(**values):
        captured["document"].update(values)

    def write_chunks(**values):
        captured["chunks"].update(values)

    monkeypatch.setattr(outbox, "upsert_document_memory", write_projection)
    monkeypatch.setattr(outbox, "upsert_document_chunks", write_chunks)
    monkeypatch.setattr(outbox, "upsert_category_document_projection", lambda **_values: None)
    source_id = str(uuid4())
    event = SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), aggregate_id=uuid4(),
        event_type="document.indexed",
        payload={
            "title": "Support Handbook", "source_type": "pdf",
            "category": "knowledge_article", "version": 2,
            "summary": "Approved support guidance.", "keywords": ["support"],
            "chunk_count": 3, "source_uri": "object://safe/source",
            "previous_document_id": str(uuid4()),
            "chunks": [{
                "chunk_id": str(uuid4()), "source_id": source_id,
                "content": "Escalate severity-one cases immediately.",
                "heading_path": ["Support", "Escalation"], "page_number": 4,
                "chunk_type": "prose", "token_count": 5, "category": "support_process",
            }],
        },
        deliveries={"postgres": "completed", "ferret": "pending"},
        status="pending", attempt_count=0, last_error=None, completed_at=None,
    )

    completed = await deliver_event(event)

    assert completed.status == "completed"
    assert completed.deliveries == {"postgres": "completed", "ferret": "completed"}
    assert captured["document"]["tenant_id"] == str(event.tenant_id)
    assert captured["document"]["document_id"] == str(event.aggregate_id)
    assert captured["document"]["summary"] == "Approved support guidance."
    assert captured["chunks"]["tenant_id"] == str(event.tenant_id)
    assert captured["chunks"]["chunks"][0]["source_id"] == source_id
    assert captured["chunks"]["chunks"][0]["heading_path"] == ["Support", "Escalation"]
    assert captured["chunks"]["chunks"][0]["chunk_type"] == "prose"
