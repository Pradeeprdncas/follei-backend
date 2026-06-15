"""Reranking — placeholder for Cohere/Mistral reranker API."""
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def rerank(query: str, results: list[dict], top_k: int | None = None) -> list[dict]:
    """
    Rerank results using a cross-encoder reranker.
    For MVP: skip reranking and just return top N from RRF.
    """
    k = top_k or _settings.TOP_K_RERANK
    # TODO: Integrate Cohere/Mistral reranker API here
    # For now, just truncate to top_k
    ranked = results[:k]
    logger.info(f"Rerank (passthrough): {len(ranked)} chunks")
    return ranked
