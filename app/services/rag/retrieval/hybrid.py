from app.services.rag.retrieval.dense import retrieve_dense
from app.services.rag.retrieval.bm25 import retrieve_bm25
from app.services.rag.retrieval.rrf import rrf_fusion
from app.services.rag.retrieval.rerank import rerank
from app.services.rag.retrieval.expansion import expand_neighbors
from app.services.rag.llm.query_expander import generate_queries

from loguru import logger


async def hybrid_retrieve(
    query: str,
    tenant_id: str
):

    queries = await generate_queries(query)

    logger.info(
        f"Running retrieval with "
        f"{len(queries)} query variants"
    )

    dense_all = []
    bm25_all = []

    for q in queries:

        logger.info(
            f"Retrieval query: {q}"
        )

        dense = await retrieve_dense(
            q,
            tenant_id,
            top_k=50
        )

        bm25 = retrieve_bm25(
            q,
            tenant_id,
            top_k=50
        )

        dense_all.extend(dense)
        bm25_all.extend(bm25)

    fused = rrf_fusion(
        dense_all,
        bm25_all
    )

    logger.info(
        f"RRF returned "
        f"{len(fused)} chunks"
    )

    expanded_chunks = expand_neighbors(
        [
            r["chunk_id"]
            for r in fused[:40]
        ]
    )

    logger.info(
        f"Expansion produced "
        f"{len(expanded_chunks)} chunks"
    )

    for i, item in enumerate(
        expanded_chunks[:10]
    ):

        logger.info(
            f"EXPANDED {i+1} | "
            f"{item['text'][:120]}"
        )

    reranked = await rerank(
        query=query,
        results=expanded_chunks,
        top_k=60
    )

    logger.info(
        f"Reranked down to "
        f"{len(reranked)} chunks"
    )

    return reranked