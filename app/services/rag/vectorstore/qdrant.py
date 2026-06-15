"""Qdrant collection management."""
from qdrant_client.models import Distance, VectorParams
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def ensure_collection():
    """Create Qdrant collection if it doesn't exist."""
    client = get_qdrant()
    collection_name = _settings.QDRANT_COLLECTION_NAME

    try:
        client.get_collection(collection_name)
        logger.info(f"Qdrant collection '{collection_name}' already exists")
    except Exception:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=_settings.QDRANT_VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection '{collection_name}' ({_settings.QDRANT_VECTOR_SIZE}d, cosine)")


def delete_collection():
    """Drop the Qdrant collection (use with caution)."""
    client = get_qdrant()
    client.delete_collection(_settings.QDRANT_COLLECTION_NAME)
    logger.warning(f"Deleted Qdrant collection '{_settings.QDRANT_COLLECTION_NAME}'")
