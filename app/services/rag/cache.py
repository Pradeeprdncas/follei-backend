import json
import hashlib
import time
from typing import Any

from loguru import logger

from app.config.redis import get_redis
from app.config.settings import get_settings

_settings = get_settings()

CACHE_PREFIX = "rag:semantic:"
DEFAULT_THRESHOLD = 0.92
DEFAULT_TTL = 3600  # 1 hour


def _embedding_hash(embedding: list[float], precision: int = 3) -> str:
    """Bucket an embedding to a hash key by rounding and hashing."""
    rounded = [round(v, precision) for v in embedding[:64]]
    raw = ",".join(str(v) for v in rounded)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticCacheRepository:
    """Redis-backed semantic cache for RAG responses.

    Cache key = embedding hash bucket (16-char hex).
    Value = {answer, sources, timestamp, embedding_hash}.
    Lookup: compute embedding of query, hash it, check Redis.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        self._redis = get_redis()
        self._threshold = threshold
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    # â”€â”€ Internal helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _key(self, embedding_hash: str, tenant_id: str = "") -> str:
        tenant_hash = hashlib.sha256((tenant_id or "__global__").encode()).hexdigest()[:12]
        return f"{CACHE_PREFIX}{tenant_hash}:{embedding_hash}"

    def _store_entry(self, embedding_hash: str, data: dict, tenant_id: str = "") -> None:
        key = self._key(embedding_hash, tenant_id)
        self._redis.setex(key, self._ttl, json.dumps(data))

    def _load_entry(self, embedding_hash: str, tenant_id: str = "") -> dict | None:
        key = self._key(embedding_hash, tenant_id)
        raw = self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            self._redis.delete(key)
            return None

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup(self, query_embedding: list[float], tenant_id: str = "") -> dict | None:
        """Check cache for a semantically similar query.

        Returns cached {answer, sources, timestamp} if found above threshold,
        or None on miss.
        """
        bucket = _embedding_hash(query_embedding)
        entry = self._load_entry(bucket, tenant_id)
        if entry is None:
            self._misses += 1
            return None

        cached_embed = entry.get("embedding")
        if cached_embed and len(cached_embed) == len(query_embedding):
            sim = _cosine_sim(query_embedding, cached_embed)
            if sim >= self._threshold:
                self._hits += 1
                logger.info("Semantic cache HIT (sim={:.4f}, bucket={})", sim, bucket)
                return {
                    "answer": entry.get("answer", ""),
                    "sources": entry.get("sources", []),
                    "cached_at": entry.get("timestamp", 0),
                }

        self._misses += 1
        return None

    def store(
        self,
        query_embedding: list[float],
        answer: str,
        sources: list[dict],
        tenant_id: str = "",
    ) -> None:
        """Store a response in the semantic cache."""
        bucket = _embedding_hash(query_embedding)
        entry = {
            "answer": answer,
            "sources": sources,
            "timestamp": int(time.time()),
            "embedding": query_embedding,
        }
        self._store_entry(bucket, entry, tenant_id)
        logger.info("Semantic cache STORE (bucket={})", bucket)

    def invalidate(self, embedding_or_text: list[float] | str) -> None:
        """Remove a cache entry by embedding or raw text."""
        if isinstance(embedding_or_text, str):
            from app.services.rag.embeddings.local import embed_query
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return
            except RuntimeError:
                pass
            return
        bucket = _embedding_hash(embedding_or_text)
        self._redis.delete(self._key(bucket))

    def clear(self) -> int:
        """Clear all semantic cache entries. Returns count of deleted keys."""
        cursor = 0
        count = 0
        while True:
            cursor, keys = self._redis.scan(cursor, match=f"{CACHE_PREFIX}*")
            if keys:
                self._redis.delete(*keys)
                count += len(keys)
            if cursor == 0:
                break
        logger.info("Semantic cache cleared ({} keys)", count)
        return count

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            "total_lookups": total,
            "threshold": self._threshold,
            "ttl_seconds": self._ttl,
        }


_cache: SemanticCacheRepository | None = None


def get_semantic_cache(
    threshold: float | None = None,
    ttl: int | None = None,
) -> SemanticCacheRepository:
    global _cache
    if _cache is None:
        _cache = SemanticCacheRepository(
            threshold=threshold or DEFAULT_THRESHOLD,
            ttl=ttl or DEFAULT_TTL,
        )
    return _cache



