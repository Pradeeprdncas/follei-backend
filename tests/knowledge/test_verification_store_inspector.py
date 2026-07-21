from types import SimpleNamespace
from uuid import uuid4

from app.routers import verification_ui


class _Rows(list):
    pass


class _Database:
    def __init__(self, row):
        self.row = row

    def execute(self, statement, params):
        assert params["tenant_id"] == self.row["tenant_id"]
        return _Rows([SimpleNamespace(_mapping=self.row)])


class _Cursor(list):
    def sort(self, *args):
        return self

    def limit(self, value):
        return _Cursor(self[:value])


class _Collection:
    def __init__(self, tenant_id, document_id):
        self.tenant_id = tenant_id
        self.document_id = document_id

    def find(self, query, projection):
        assert query == {"tenant_id": self.tenant_id, "document_id": self.document_id}
        assert projection == {"_id": 0}
        return _Cursor([{
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "summary": "Clean memory summary",
            "credential": "must-not-leak",
        }])


class _ContextDatabase:
    def __init__(self, tenant_id, document_id):
        self.collection = _Collection(tenant_id, document_id)

    def __getitem__(self, name):
        assert name == "knowledge_document_memory"
        return self.collection


def test_store_inspector_returns_content_without_vectors_or_credentials(monkeypatch):
    tenant_id = str(uuid4())
    document_id = uuid4()
    chunk_id = uuid4()
    db = _Database({
        "id": chunk_id,
        "document_id": document_id,
        "document_title": "Product guide",
        "chunk_index": 0,
        "content": "Actual canonical content",
        "token_count": 3,
        "metadata": {"page": 1},
        "created_at": None,
        "tenant_id": tenant_id,
    })

    class _Qdrant:
        def scroll(self, **kwargs):
            assert kwargs["with_vectors"] is False
            return ([SimpleNamespace(
                id=chunk_id,
                payload={
                    "tenant_id": tenant_id,
                    "document_id": str(document_id),
                    "text": "Actual semantic content",
                    "access_token": "must-not-leak",
                },
            )], None)

    monkeypatch.setattr(verification_ui, "get_qdrant", lambda: _Qdrant())
    monkeypatch.setattr(
        verification_ui,
        "get_context_database",
        lambda: _ContextDatabase(tenant_id, str(document_id)),
    )

    result = verification_ui.tenant_store_content(
        document_id=document_id,
        limit=10,
        tenant_id=tenant_id,
        db=db,
    )

    assert result["postgres"]["chunks"][0]["content"] == "Actual canonical content"
    assert result["qdrant"]["points"][0]["payload"]["text"] == "Actual semantic content"
    assert result["qdrant"]["points"][0]["payload"]["access_token"] == "[redacted]"
    assert result["qdrant"]["vectors_included"] is False
    assert result["ferretdb"]["records"][0]["record"]["credential"] == "[redacted]"
