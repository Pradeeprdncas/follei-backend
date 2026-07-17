from app.services.rag.retrieval.dense import retrieve_dense
from app.services.rag.retrieval.bm25 import retrieve_bm25
from app.services.rag.retrieval.rrf import rrf_fusion
from app.services.rag.retrieval.rerank import rerank
from app.services.rag.retrieval.expansion import expand_neighbors
from app.services.rag.llm.query_expander import generate_queries
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def hybrid_retrieve(query: str, tenant_id: str) -> list[dict]:
    """Retrieve efficiently; query expansion is optional because it adds an LLM round trip."""
    queries = await generate_queries(query) if _settings.RAG_ENABLE_QUERY_EXPANSION else [query]
    queries = queries[:max(1, _settings.RAG_QUERY_VARIANTS)]
    dense_all: list[dict] = []
    bm25_all: list[dict] = []
    for item in queries:
        dense_all.extend(await retrieve_dense(item, tenant_id, top_k=20))
        bm25_all.extend(retrieve_bm25(item, tenant_id, top_k=20))

    fused = rrf_fusion(dense_all, bm25_all)
    expanded_chunks = expand_neighbors([result["chunk_id"] for result in fused[:20]])
    reranked = await rerank(query=query, results=expanded_chunks, top_k=_settings.TOP_K_RERANK)
    logger.info(f"Hybrid retrieval variants={len(queries)} dense={len(dense_all)} bm25={len(bm25_all)} final={len(reranked)}")
    return reranked
