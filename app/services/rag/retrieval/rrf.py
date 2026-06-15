"""Reciprocal Rank Fusion (RRF) — merge dense + BM25 results."""
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def rrf_fusion(dense_results: list[dict], bm25_results: list[dict], k: int | None = None) -> list[dict]:
    """
    Merge two ranked lists using RRF.
    score = sum(1 / (k + rank)) for each list the item appears in.
    Returns list sorted by fused score descending.
    """
    k_val = k or getattr(_settings, "RRF_K", 60) or 60
    scores = {}

    # Dense scores (ranked by score, so index = rank-1)
    for rank, item in enumerate(dense_results, start=1):
        cid = item["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_val + rank)

    # BM25 scores
    for rank, item in enumerate(bm25_results, start=1):
        cid = item["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_val + rank)

    # Sort by fused score
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    dense_map = {r["chunk_id"]: r for r in dense_results}
    bm25_map = {r["chunk_id"]: r for r in bm25_results}

    results = []
    for cid, score in sorted_items:
        # Determine which source object contains our matching chunk details
        source_item = dense_map.get(cid) or bm25_map.get(cid) or {}
        
        # FIX: Explicitly gather properties into the payload dict so downstream steps don't receive an empty text string
        payload = {
            "text": source_item.get("text", ""),
            "page": source_item.get("page", 0),
            "heading": source_item.get("heading"),
            "chunk_index": source_item.get("chunk_index", 0)
        }

        results.append({
            "chunk_id": cid,
            "score": score,
            "payload": payload,
        })

    logger.info(f"RRF fusion: {len(results)} unique chunks from dense({len(dense_results)}) + bm25({len(bm25_results)})")
    return results