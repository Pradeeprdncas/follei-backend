"""
End-to-end retrieval pipeline: query → context.
"""

from app.services.rag.retrieval.hybrid import hybrid_retrieve
from app.services.rag.context.builder import build_context
from app.services.rag.context.compressor import compress_context
from app.config.database import SessionLocal
from app.repositories.chunk import ChunkRepository
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

    db = SessionLocal()
    try:
        chunks_by_id = {str(chunk.id): chunk for chunk in ChunkRepository(db).get_by_ids(chunk_ids)}
        ranked_chunks = [chunks_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks_by_id]
        compressed_chunks = compress_context(ranked_chunks, max_tokens=_settings.MAX_CONTEXT_TOKENS)
        selected_ids = [str(chunk.id) for chunk in compressed_chunks]
        context = build_context(selected_ids)
    finally:
        db.close()

    logger.info(
        f"Retrieval pipeline: {len(chunk_ids)} chunks -> {len(selected_ids)} compressed chunks; "
        f"context={context[:500]!r}"
    )

    return context, selected_ids