"""Mistral embedding API client."""
import httpx
import asyncio
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Call Mistral embedding API for a batch of texts.
    Returns list of embedding vectors.
    """
    if not texts:
        return []

    # Mistral embeds in batches of up to 96
    batch_size = 96
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{_settings.MISTRAL_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                    json={
                        "model": _settings.MISTRAL_EMBEDDING_MODEL,
                        "input": batch,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(embeddings)
                logger.info(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")
        except Exception as e:
            logger.error(f"Embedding batch failed: {e}")
            raise

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    embeddings = await embed_texts([text])
    return embeddings[0]
