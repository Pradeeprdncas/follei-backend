"""Optional local-model query expansion."""
from __future__ import annotations

import json

from loguru import logger

from app.services.ai.local_llm_client import complete


async def generate_queries(query: str) -> list[str]:
    prompt = f"""Generate five alternate retrieval queries for the query below.
Return only JSON shaped as {{"queries": ["...", "..."]}}.
Original query: {query}"""
    try:
        raw = await complete(
            [{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=256,
        )
        generated = json.loads(raw).get("queries", [])
        result = [query]
        for item in generated:
            if isinstance(item, str) and item.strip() and item not in result:
                result.append(item.strip())
        return result
    except Exception as exc:
        logger.warning("Query expansion failed: {}", exc)
        return [query]
