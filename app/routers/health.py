"""Health check endpoints."""
from fastapi import APIRouter
from sqlalchemy import text
from app.config.database import engine
from app.config.redis import get_redis
from app.config.qdrant import get_qdrant
from app.config.kafka import get_producer
from app.config.ferretdb import get_context_database
from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.services.knowledge.object_storage import ensure_bucket
from loguru import logger

router = APIRouter(prefix="/health", tags=["health"])
_settings = get_settings()


@router.get("/")
async def health_check():
    """Check all service connections."""
    status = {
        "api": "ok",
        "postgres": "unknown",
        "redis": "unknown",
        "qdrant": "unknown",
        "kafka": "unknown",
        "ferretdb": "unknown",
        "object_storage": "unknown",
    }

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {e}"

    try:
        redis = get_redis()
        redis.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {e}"

    try:
        qdrant = get_qdrant()
        qdrant.get_collections()
        status["qdrant"] = "ok"
    except Exception as e:
        status["qdrant"] = f"error: {e}"

    try:
        producer = get_producer()
        partitions = producer.partitions_for(_settings.KAFKA_TOPIC_INDEXING)
        status["kafka"] = "ok" if partitions else "error: indexing topic has no partitions"
    except Exception as e:
        status["kafka"] = f"error: {e}"

    try:
        get_context_database().command("ping")
        status["ferretdb"] = "ok"
    except Exception as e:
        status["ferretdb"] = f"error: {e}"

    try:
        ensure_bucket()
        status["object_storage"] = "ok" if _settings.OBJECT_STORAGE_ENABLED else "disabled"
    except Exception as e:
        status["object_storage"] = f"error: {e}"

    queues = {"indexing": {}, "knowledge_sync": {}}
    try:
        with SessionLocal() as db:
            for value in ("queued", "processing", "retrying", "failed", "dead_lettered"):
                queues["indexing"][value] = db.query(IndexingJob).filter(IndexingJob.status == value).count()
            for value in ("pending", "processing", "retrying"):
                queues["knowledge_sync"][value] = db.query(KnowledgeSyncEvent).filter(KnowledgeSyncEvent.status == value).count()
    except Exception as e:
        queues["error"] = str(e)

    all_ok = all(v in {"ok", "disabled"} for v in status.values())
    return {"status": "healthy" if all_ok else "degraded", "services": status, "queues": queues}
