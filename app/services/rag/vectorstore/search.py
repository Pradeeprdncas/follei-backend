"""Search Qdrant vector store."""
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def dense_search(query_vector: list[float], tenant_id: str, top_k: int | None = None, filters: dict | None = None) -> list[dict]:
    """
    Dense vector search in Qdrant.
    Returns list of {"chunk_id": str, "score": float, "payload": dict}.
    """
    k = top_k or _settings.TOP_K_RETRIEVAL
    client = get_qdrant()
    collection = _settings.QDRANT_COLLECTION_NAME

    # Build filter for tenant_id
    qdrant_filter = None
    if tenant_id:
        from qdrant_client.models import FieldCondition, MatchValue, Filter
        qdrant_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            ]
        )

    results = client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=k,
        query_filter=qdrant_filter,
        with_payload=True,
    )

    out = []
    for r in results:
        out.append({
            "chunk_id": r.id,
            "score": r.score,
            "payload": r.payload,
        })

    logger.info(f"Dense search: {len(out)} results for tenant={tenant_id}")
    return out
