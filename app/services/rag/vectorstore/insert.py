"""Insert chunks into Qdrant vector store."""
from qdrant_client.models import PointStruct
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


def insert_chunks(chunk_ids: list[str], embeddings: list[list[float]], payloads: list[dict]) -> None:
    """
    Upsert chunks into Qdrant.
    chunk_ids: list of UUID strings
    embeddings: list of vector lists
    payloads: list of metadata dicts
    """
    client = get_qdrant()
    collection = _settings.QDRANT_COLLECTION_NAME

    points = []
    for cid, vec, payload in zip(chunk_ids, embeddings, payloads):
        points.append(
            PointStruct(
                id=cid,
                vector=vec,
                payload=payload,
            )
        )

    client.upsert(collection_name=collection, points=points)
    logger.info(f"Inserted {len(points)} chunks into Qdrant")
