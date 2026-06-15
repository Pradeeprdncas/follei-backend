"""Redis client singleton."""
import redis
from app.config.settings import get_settings

_settings = get_settings()

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Lazy singleton Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            _settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client
