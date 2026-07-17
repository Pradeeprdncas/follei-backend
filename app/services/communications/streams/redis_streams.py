"""Redis stream producer/consumer for async tracking events.

Tracking endpoints (open, click, delivery, bounce, etc.) write events
to Redis streams instead of updating analytics directly. Workers consume
these streams and update the database asynchronously.
"""
import json
import uuid
from typing import Any
from loguru import logger

from app.config.redis import get_redis


STREAM_TRACKING = "campaign:tracking"
STREAM_ANALYTICS = "campaign:analytics"
STREAM_EVENTS = "campaign:events"

MAX_STREAM_LENGTH = 100000


def push_tracking_event(event_type: str, tenant_id: str,
                         campaign_id: str, message_id: str,
                         data: dict | None = None) -> bool:
    """Push a tracking event to Redis stream for async processing."""
    try:
        redis = get_redis()
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "message_id": message_id,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "data": json.dumps(data or {}),
        }
        redis.xadd(STREAM_TRACKING, event, maxlen=MAX_STREAM_LENGTH)
        return True
    except Exception as e:
        logger.error(f"Failed to push tracking event to Redis: {e}")
        return False


def push_analytics_event(event_type: str, tenant_id: str,
                          campaign_id: str, data: dict) -> bool:
    """Push an analytics event to Redis stream."""
    try:
        redis = get_redis()
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "data": json.dumps(data),
        }
        redis.xadd(STREAM_ANALYTICS, event, maxlen=MAX_STREAM_LENGTH)
        return True
    except Exception as e:
        logger.error(f"Failed to push analytics event to Redis: {e}")
        return False


def consume_tracking_events(batch_size: int = 10, block_ms: int = 2000) -> list[dict]:
    """Consume pending tracking events from Redis stream."""
    try:
        redis = get_redis()
        results = redis.xreadgroup(
            groupname="tracking-workers",
            consumername=f"worker-{uuid.uuid4().hex[:8]}",
            streams={STREAM_TRACKING: ">"},
            count=batch_size,
            block=block_ms,
        )
        events = []
        for stream, messages in results:
            for msg_id, msg_data in messages:
                events.append({"stream_id": msg_id, **msg_data})
                redis.xack(STREAM_TRACKING, "tracking-workers", msg_id)
        return events
    except Exception as e:
        logger.error(f"Failed to consume tracking events: {e}")
        return []


def ensure_consumer_group() -> None:
    """Ensure consumer groups exist for all streams."""
    try:
        redis = get_redis()
        for stream, group in [
            (STREAM_TRACKING, "tracking-workers"),
            (STREAM_ANALYTICS, "analytics-workers"),
            (STREAM_EVENTS, "event-workers"),
        ]:
            try:
                redis.xgroup_create(stream, group, id="0", mkstream=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to ensure consumer groups: {e}")
