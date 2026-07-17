import os
from uuid import UUID


def delete_document_vectors(tenant_id: UUID, document_id: UUID) -> None:
    """
    Best-effort cleanup for document vectors.

    The API should not fail document deletion just because Qdrant is not configured
    in a local/dev environment.
    """
    qdrant_url = os.getenv("QDRANT_URL")
    collection_name = os.getenv("QDRANT_COLLECTION", "document_chunks")
    if not qdrant_url:
        return

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models
    except ImportError:
        return

    try:
        client = QdrantClient(
            url=qdrant_url,
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=str(tenant_id)),
                        ),
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        ),
                    ]
                )
            ),
        )
    except Exception:
        return
