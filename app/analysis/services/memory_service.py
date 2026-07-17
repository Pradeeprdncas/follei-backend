import json
import logging
from app.config.redis import get_redis
from app.config.settings import get_settings

_settings = get_settings()

logger = logging.getLogger(__name__)


class MemoryService:
    SESSION_PREFIX = "assistant:session:"

    @classmethod
    def _key(cls, session_id: str) -> str:
        return f"{cls.SESSION_PREFIX}{session_id}"

    @classmethod
    def append_user_message(cls, session_id: str, content: str):
        redis = get_redis()
        key = cls._key(session_id)
        record = json.dumps({"role": "user", "content": content})
        redis.lpush(key, record)
        redis.expire(key, 60 * 60 * 24)
        logger.debug("Appended user message to %s", session_id)

    @classmethod
    def append_assistant_message(cls, session_id: str, content: str):
        redis = get_redis()
        key = cls._key(session_id)
        record = json.dumps({"role": "assistant", "content": content})
        redis.lpush(key, record)
        redis.expire(key, 60 * 60 * 24)
        logger.debug("Appended assistant message to %s", session_id)

    @classmethod
    def get_history(cls, session_id: str, limit: int = None):
        redis = get_redis()
        key = cls._key(session_id)
        limit = limit or _settings.MAX_HISTORY
        records = redis.lrange(key, 0, limit - 1)
        messages = [json.loads(item) for item in reversed(records)]
        return messages

    @classmethod
    def clear_session(cls, session_id: str):
        redis = get_redis()
        key = cls._key(session_id)
        redis.delete(key)
        logger.info("Cleared session memory %s", session_id)


memory_service = MemoryService()
