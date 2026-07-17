from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.knowledge.outbox import deliver_event


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