"""Reciprocal Rank Fusion (RRF) — merge dense + BM25 results."""
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def rrf_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int | None = None,
) -> list[dict]:

    k_val = k or getattr(_settings, "RRF_K", 60)

    scores = {}
    sources = {}

    for rank, item in enumerate(dense_results, start=1):

        cid = item["chunk_id"]

        scores[cid] = scores.get(cid, 0.0) + (
            1.0 / (k_val + rank)
        )

        sources.setdefault(cid, set()).add("dense")

    for rank, item in enumerate(bm25_results, start=1):

        cid = item["chunk_id"]

        scores[cid] = scores.get(cid, 0.0) + (
            1.0 / (k_val + rank)
        )

        sources.setdefault(cid, set()).add("bm25")

    dense_map = {
        r["chunk_id"]: r
        for r in dense_results
    }

    bm25_map = {
        r["chunk_id"]: r
        for r in bm25_results
    }

    results = []

    for cid, score in sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        source_item = (
            dense_map.get(cid)
            or bm25_map.get(cid)
            or {}
        )

        payload = source_item.get("payload")

        if not payload:

            payload = {
                "text": source_item.get(
                    "text",
                    ""
                ),
                "page": source_item.get(
                    "page",
                    0
                ),
                "heading": source_item.get(
                    "heading"
                ),
                "chunk_index": source_item.get(
                    "chunk_index",
                    0
                )
            }
        results.append({
            "chunk_id": cid,
            "score": score,
            "text": source_item.get("text", ""),
            "page": source_item.get("page"),
            "heading": source_item.get("heading"),
            "chunk_index": source_item.get("chunk_index")
        })
    return results