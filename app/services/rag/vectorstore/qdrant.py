"""Qdrant collection management and filter indexes."""
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()
_FILTER_FIELDS = ("tenant_id", "approval_status", "document_id", "source_type", "sensitivity")


def ensure_collection() -> None:
    """Create the chunk collection and the indexes used by every tenant query."""
    client = get_qdrant()
    collection_name = _settings.QDRANT_COLLECTION_NAME
    try:
        client.get_collection(collection_name)
        logger.info(f"Qdrant collection '{collection_name}' already exists")
    except Exception:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=_settings.QDRANT_VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection '{collection_name}'")

    # These turn tenant/approval filtered searches into indexed lookups instead of scans.
    for field in _FILTER_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception as exc:
            # Qdrant returns an error when the index already exists; it is safe to continue.
            logger.debug(f"Qdrant payload index '{field}' unchanged: {exc}")


def delete_collection() -> None:
    """Drop the Qdrant collection (use with caution)."""
    client = get_qdrant()
    client.delete_collection(_settings.QDRANT_COLLECTION_NAME)
    logger.warning(f"Deleted Qdrant collection '{_settings.QDRANT_COLLECTION_NAME}'")
