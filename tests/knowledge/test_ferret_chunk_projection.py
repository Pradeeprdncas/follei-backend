from app.services.knowledge import memory_store


class _Collection:
    def __init__(self):
        self.rows = {}
        self.deleted = []

    def replace_one(self, key, value, upsert=False):
        self.rows[(key["tenant_id"], key["chunk_id"])] = value

    def delete_many(self, query):
        self.deleted.append(query)


def test_ferret_chunk_projection_writes_content_and_required_metadata(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(memory_store, "get_context_database", lambda: {"knowledge_chunks": collection})

    count = memory_store.upsert_document_chunks(
        tenant_id="tenant-a",
        document_id="document-a",
        chunks=[{
            "chunk_id": "chunk-a", "source_id": "source-a", "content": "Enterprise costs $999.",
            "category": "pricing", "heading_path": ["Plans", "Enterprise"],
            "page_number": 3, "chunk_type": "table", "token_count": 3,
        }],
    )

    assert count == 1
    stored = collection.rows[("tenant-a", "chunk-a")]
    assert stored["source_id"] == "source-a"
    assert stored["content"] == "Enterprise costs $999."
    assert stored["heading_path"] == ["Plans", "Enterprise"]
    assert stored["chunk_type"] == "table"
    assert stored["token_count"] == 3
    assert collection.deleted[0]["chunk_id"] == {"$nin": ["chunk-a"]}
