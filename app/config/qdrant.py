"""Qdrant vector DB client singleton."""
from qdrant_client import QdrantClient
from app.config.settings import get_settings

_settings = get_settings()

_qdrant_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    """Lazy singleton Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        kwargs = {"url": _settings.QDRANT_URL}
        if _settings.QDRANT_API_KEY:
            kwargs["api_key"] = _settings.QDRANT_API_KEY
        _qdrant_client = QdrantClient(**kwargs)
    return _qdrant_client
