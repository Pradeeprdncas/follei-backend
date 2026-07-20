import re

from loguru import logger


_STOPWORDS = {
    "the", "and", "for", "from", "what", "which", "when", "where", "who", "why", "how",
    "does", "have", "with", "about", "tell", "please", "this", "that", "these", "those",
    "your", "our", "are", "was", "were", "can", "could", "would", "should", "according",
    "each", "contain", "contains", "into",
}


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


async def rerank(
    query: str,
    results: list[dict],
    top_k: int = 10
):

    if not results:
        return []

    seen = set()
    candidates = []
    query_terms = _terms(query)

    for item in results:

        cid = item["chunk_id"]

        if cid in seen:
            continue

        seen.add(cid)

        text = item.get("text", "")

        if not text.strip():
            continue

        text_terms = _terms(" ".join(filter(None, [item.get("heading"), text])))
        lexical_score = len(query_terms.intersection(text_terms)) / len(query_terms) if query_terms else 0.0
        candidates.append({**item, "rerank_score": lexical_score})

    # Preserve hybrid/vector order as the tie-breaker.  Only prune when one or
    # more candidates has a strong direct match; weak-overlap and synonym-heavy
    # queries keep the semantic ordering instead of being discarded.
    ranked = sorted(enumerate(candidates), key=lambda pair: (-pair[1]["rerank_score"], pair[0]))
    ranked = [item for _, item in ranked]
    best_score = ranked[0]["rerank_score"] if ranked else 0.0
    if best_score >= 0.35:
        cutoff = max(0.15, best_score * 0.5)
        ranked = [item for item in ranked if item["rerank_score"] >= cutoff]

    logger.info(
        f"Rerank kept {len(ranked[:top_k])} chunks best_lexical_score={best_score:.3f}"
    )

    return ranked[:top_k]
