"""Embedding generation using local Nomic-embed-text-v1.5 with query cache."""
from app.services.ai.model_manager import _get_loaded_model_unsafe, get_model_manager
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()

_query_cache: dict[str, list[float]] = {}
_QUERY_CACHE_MAX = 1024


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings (fast-path, no Router, no lock overhead)."""
    if not texts:
        return []

    try:
        loader = _get_loaded_model_unsafe("embedding", _settings.EMBED_MODEL)
        if loader is None:
            manager = get_model_manager()
            model_info = await manager.get_model("embedding", _settings.EMBED_MODEL)
            loader = model_info["loader"]

        embeddings = await loader.infer(texts)
        return embeddings

    except Exception as e:
        logger.error(f"Local embedding failed: {e}")
        raise


async def embed_query(text: str) -> list[float]:
    """Embed a single query string locally with LRU-style cache."""
    global _query_cache
    if text in _query_cache:
        return _query_cache[text]
    embeddings = await embed_texts([text])
    result = embeddings[0] if embeddings else []
    if len(_query_cache) >= _QUERY_CACHE_MAX:
        _query_cache.clear()
    _query_cache[text] = result
    return result
