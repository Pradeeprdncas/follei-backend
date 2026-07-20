"""Dense vector retrieval pipeline using Qdrant."""
from app.config.qdrant import get_qdrant
from app.services.rag.embeddings.mistral import embed_texts
from app.config.settings import get_settings
from loguru import logger
from app.services.rag.retrieval.approval import approved_filter

_settings = get_settings()


async def retrieve_dense(query: str, tenant_id: str, top_k: int = 5, category: str | None = None, require_approved: bool | None = None) -> list[dict]:
    """Retrieves contextually relevant document chunks via dense vector lookup."""
    client = get_qdrant()
    collection_name = _settings.QDRANT_COLLECTION_NAME

    # 1. Generate the query vector embedding via Mistral
    embeddings = await embed_texts([query])
    if not embeddings:
        logger.error("Failed to generate vector embedding for the query.")
        return []
    query_vector = embeddings[0]

    try:
        # 2. Modern Qdrant API call replacing client.search()
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,  # Modern parameter accepts raw list[float]
            limit=top_k,
            # Filter matches by user tenancy boundary if applicable
            query_filter=approved_filter(tenant_id) if tenant_id else None
        )

        # 3. Formulate standard chunk dictionaries from ScoredPoints list
        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append({
                "chunk_id": str(point.id),
                "score": point.score,
                "text": payload.get("text", ""),
                "page": payload.get("page", 0),
                "heading": payload.get("heading"),
                "chunk_index": payload.get("chunk_index", 0),
                "heading_path": payload.get("heading_path") or payload.get("section_path", []),
                "approval_status": payload.get("approval_status", "draft"),
                "source_type": payload.get("source_type"),
                "sensitivity": payload.get("sensitivity"),
                "document_id": payload.get("document_id"),
                "tenant_id": payload.get("tenant_id")
            })

        logger.info(f"Dense vector search retrieved {len(results)} matches.")
        return results

    except Exception as e:
        logger.error(f"Qdrant query execution aborted: {str(e)}")
        return []
