"""Health check endpoints."""
from fastapi import APIRouter
from app.config.database import engine
from app.config.redis import get_redis
from app.config.qdrant import get_qdrant
from app.config.kafka import get_producer
from loguru import logger

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check():
    """Check all service connections."""
    status = {
        "api": "ok",
        "postgres": "unknown",
        "redis": "unknown",
        "qdrant": "unknown",
        "kafka": "unknown",
    }

    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
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
        status["kafka"] = "ok"
    except Exception as e:
        status["kafka"] = f"error: {e}"

    all_ok = all(v == "ok" for v in status.values())
    return {"status": "healthy" if all_ok else "degraded", "services": status}
