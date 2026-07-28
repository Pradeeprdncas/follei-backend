from copy import deepcopy

from app.services.knowledge import memory_store


class FakeCollection:
    def __init__(self):
        self.document = None

    def find_one(self, key, _projection=None):
        if self.document and all(self.document.get(k) == v for k, v in key.items()):
            return deepcopy(self.document)
        return None

    def replace_one(self, _key, document, upsert=False):
        assert upsert is True
        self.document = deepcopy(document)


def test_nurture_memory_keeps_user_and_ai_and_is_idempotent(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(
        memory_store,
        "get_context_database",
        lambda: {"tenant_context": collection},
    )
    kwargs = {
        "tenant_id": "tenant-1",
        "lead_id": "lead-1",
        "conversation_id": "conversation-1",
        "turn_id": "conversation-1:2",
        "user_text": "We need deployment in six weeks.",
        "assistant_text": "I can help confirm the implementation timeline.",
        "channel": "voice",
        "citations": [{"chunk_id": "chunk-1"}],
    }

    first = memory_store.append_lead_nurture_turn(**kwargs)
    second = memory_store.append_lead_nurture_turn(**kwargs)

    assert first["nurture_turn_count"] == 1
    assert second["nurture_turn_count"] == 1
    assert second["nurture_history"] == [{
        "turn_id": "conversation-1:2",
        "conversation_id": "conversation-1",
        "channel": "voice",
        "user": "We need deployment in six weeks.",
        "assistant": "I can help confirm the implementation timeline.",
        "citations": [{"chunk_id": "chunk-1"}],
        "at": first["nurture_history"][0]["at"],
    }]
