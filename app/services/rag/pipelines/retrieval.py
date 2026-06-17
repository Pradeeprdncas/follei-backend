"""
End-to-end retrieval pipeline: query → context.
"""

from app.services.rag.retrieval.hybrid import hybrid_retrieve
from app.services.rag.context.builder import build_context
from app.services.rag.context.compressor import compress_context
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def retrieve_context(
    query: str,
    tenant_id: str
) -> tuple[str, list[str]]:

    results = await hybrid_retrieve(
        query,
        tenant_id
    )

    if not results:

        logger.warning(
            f"No chunks retrieved for query='{query[:50]}...'"
        )

        return "", []

    # convert reranked results into plain UUID list

    chunk_ids = [
        item["chunk_id"]
        for item in results
        if item.get("chunk_id")
    ]

    context = build_context(chunk_ids)

    compressed = compress_context(
        context,
        max_tokens=_settings.MAX_CONTEXT_TOKENS
    )

    logger.info(
        f"Retrieval pipeline: "
        f"{len(chunk_ids)} chunks -> "
        f"{len(compressed)} chars"
    )

    return compressed, chunk_ids