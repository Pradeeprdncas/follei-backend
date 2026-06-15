"""Hybrid retrieval: dense + BM25 + RRF + rerank."""
from app.services.rag.retrieval.dense import retrieve_dense
from app.services.rag.retrieval.bm25 import retrieve_bm25
from app.services.rag.retrieval.rrf import rrf_fusion
from app.services.rag.retrieval.rerank import rerank
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def hybrid_retrieve(query: str, tenant_id: str) -> list[dict]:
    """
    Full hybrid retrieval pipeline:
    1. Dense vector search
    2. BM25 keyword search
    3. RRF fusion
    4. Rerank (passthrough for MVP)
    Returns top chunks with metadata.
    """
    dense_results = await retrieve_dense(query, tenant_id, top_k=_settings.TOP_K_RETRIEVAL)
    bm25_results = retrieve_bm25(query, tenant_id, top_k=_settings.TOP_K_RETRIEVAL)
    fused = rrf_fusion(dense_results, bm25_results)
    ranked = await rerank(query, fused, top_k=_settings.TOP_K_RERANK)
    logger.info(f"Hybrid retrieve: {len(ranked)} final chunks")
    return ranked
