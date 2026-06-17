from loguru import logger


async def rerank(
    query: str,
    results: list[dict],
    top_k: int = 10
):

    if not results:
        return []

    seen = set()
    ranked = []

    for item in results:

        cid = item["chunk_id"]

        if cid in seen:
            continue

        seen.add(cid)

        text = item.get("text", "")

        if not text.strip():
            continue

        ranked.append(item)

    logger.info(
        f"Rerank kept {len(ranked)} chunks"
    )

    return ranked[:top_k]