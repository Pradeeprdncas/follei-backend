"""TTL Caching engine for MCP execution outputs."""
import asyncio
import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """Async-safe memory cache with key TTL expiry."""

    def __init__(self, default_ttl: float = 300.0) -> None:
        self.default_ttl = default_ttl
        # Store key -> (value, expiry_timestamp)
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieves a cached value if exists and not expired."""
        async with self._lock:
            if key not in self._cache:
                return None
            val, expiry = self._cache[key]
            if time.time() > expiry:
                # Evict expired key
                del self._cache[key]
                return None
            return val

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Sets a cached value with a specific TTL."""
        ttl_val = ttl if ttl is not None else self.default_ttl
        expiry = time.time() + ttl_val
        async with self._lock:
            self._cache[key] = (value, expiry)

    async def invalidate(self, key: str) -> None:
        """Invalidates a single key."""
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clears all cached items."""
        async with self._lock:
            self._cache.clear()
