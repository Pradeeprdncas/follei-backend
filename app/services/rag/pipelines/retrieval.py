"""End-to-end retrieval pipeline: query → context."""
from app.services.rag.retrieval.hybrid import hybrid_retrieve
from app.services.rag.context.builder import build_context
from app.services.rag.context.compressor import compress_context
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def retrieve_context(query: str, tenant_id: str) -> tuple[str, list[str]]:
    """
    Retrieve and compress context for a query.
    Returns (context_string, chunk_ids).
    """
    results = await hybrid_retrieve(query, tenant_id)
    chunk_ids = [r["chunk_id"] for r in results]

    if not chunk_ids:
        logger.warning(f"No chunks retrieved for query='{query[:50]}...'")
        return "", []

    context = build_context(chunk_ids)
    compressed = compress_context(context, max_tokens=_settings.MAX_CONTEXT_TOKENS)
    logger.info(f"Retrieval pipeline: {len(chunk_ids)} chunks → {len(compressed)} chars context")
    return compressed, chunk_ids
