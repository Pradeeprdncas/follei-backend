"""Redis Service - Production Redis health checker with graceful degradation."""
from typing import Dict, Any
from loguru import logger


class RedisService:
    """Production Redis service with graceful skip.

    - connect(): Establish connection
    - ping(): Test connectivity
    - health(): Return health status
    Never crashes startup.
    """

    def __init__(self):
        self._client = None
        self._enabled = True
        self._configured = False
        self._init()

    def _init(self):
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            # Check if redis config exists
            redis_host = getattr(settings, 'REDIS_HOST', None) or \
                         getattr(settings, 'REDIS_URL', None)
            self._enabled = redis_host is not None
            self._configured = True
        except Exception:
            self._enabled = False
            self._configured = False

    def connect(self):
        """Establish Redis connection."""
        if not self._enabled:
            return False
        try:
            from app.config.redis import get_redis
            self._client = get_redis()
            return self._client is not None
        except Exception:
            self._enabled = False
            return False

    def ping(self) -> bool:
        """Test Redis connectivity."""
        if not self._enabled:
            return False
        try:
            import asyncio
            result = asyncio.run(self._client.ping())
            return result is True
        except Exception:
            return False

    def health(self) -> Dict[str, Any]:
        """Get Redis health status."""
        try:
            if self.ping():
                return {"redis": "healthy", "status": "ok"}
        except Exception:
            pass
        if not self._enabled:
            return {"redis": "disabled", "status": "skipped"}
        return {"redis": "unreachable", "status": "degraded"}


# Singleton
_redis_service: RedisService = None


def get_redis_service() -> RedisService:
    """Get or create singleton Redis service."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service