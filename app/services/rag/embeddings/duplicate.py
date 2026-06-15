"""Duplicate detection using Redis + hash."""
import hashlib
from app.config.redis import get_redis
from loguru import logger


def hash_text(text: str) -> str:
    """SHA-256 hash of text for dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_duplicate(text: str) -> str | None:
    """
    Check if text hash exists in Redis.
    Returns the hash if duplicate, None if new.
    """
    h = hash_text(text)
    redis = get_redis()
    if redis.exists(f"embed:hash:{h}"):
        logger.info(f"Duplicate chunk detected (hash={h[:16]}...)")
        return h
    return None


def mark_embedded(text: str, chunk_id: str) -> str:
    """Mark a text hash as embedded in Redis."""
    h = hash_text(text)
    redis = get_redis()
    redis.setex(f"embed:hash:{h}", 86400 * 7, chunk_id)  # 7-day TTL
    return h
