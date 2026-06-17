import json
import httpx

from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def generate_queries(query: str) -> list[str]:
    """
    Generate alternate retrieval queries.

    Returns:
    [
        original query,
        variation 1,
        variation 2,
        ...
    ]
    """

    prompt = f"""
You are a retrieval optimization engine.

Generate 5 alternate search queries
that may retrieve different but relevant
documentation chunks.

Original Query:

{query}

Return ONLY JSON.

Format:

{{
    "queries": [
        "...",
        "...",
        "..."
    ]
}}
"""

    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={
                    "Authorization":
                    f"Bearer {_settings.MISTRAL_API_KEY}"
                },
                json={
                    "model":
                    _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0,
                    "response_format": {
                        "type": "json_object"
                    }
                }
            )

        resp.raise_for_status()

        content = (
            resp.json()
            ["choices"][0]
            ["message"]["content"]
        )

        parsed = json.loads(content)

        generated = parsed.get(
            "queries",
            []
        )

        final_queries = [query]

        for q in generated:

            if (
                isinstance(q, str)
                and q.strip()
                and q not in final_queries
            ):
                final_queries.append(q)

        logger.info(
            f"Generated {len(final_queries)} retrieval queries"
        )

        return final_queries

    except Exception as e:

        logger.warning(
            f"Query expansion failed: {e}"
        )

        return [query]