from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from app.config.redis import get_redis

logger = logging.getLogger(__name__)


class RealtimeHub:
    """Redis-backed cross-process fan-out with a process-local fallback using Follei Redis."""

    _subscribers: dict[str, set[WebSocket]] = defaultdict(set)
    _lock = asyncio.Lock()
    _listeners: dict[str, asyncio.Task] = {}
    _listener_ready: dict[str, asyncio.Event] = {}
    CHANNEL_PREFIX = "assistant:lead-scores:"

    @classmethod
    async def connect(cls, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        ready = None
        async with cls._lock:
            cls._subscribers[session_id].add(websocket)
            try:
                redis = get_redis()
                needs_listener = redis is not None and session_id not in cls._listeners
            except Exception:
                needs_listener = False
            if needs_listener:
                ready = asyncio.Event()
                cls._listener_ready[session_id] = ready
                cls._listeners[session_id] = asyncio.create_task(cls._redis_listener(session_id))
        if ready is not None:
            await asyncio.wait_for(ready.wait(), timeout=3.0)

    @classmethod
    async def disconnect(cls, session_id: str, websocket: WebSocket) -> None:
        async with cls._lock:
            subscribers = cls._subscribers.get(session_id)
            if subscribers is not None:
                subscribers.discard(websocket)
                if not subscribers:
                    cls._subscribers.pop(session_id, None)
                    task = cls._listeners.pop(session_id, None)
                    cls._listener_ready.pop(session_id, None)
                    if task:
                        task.cancel()

    @classmethod
    async def publish(cls, session_id: str, event: dict[str, Any]) -> None:
        try:
            redis = get_redis()
            await redis.publish(cls.CHANNEL_PREFIX + session_id, json.dumps(event))
            return
        except Exception:
            pass
        await cls._broadcast_local(session_id, event)

    @classmethod
    async def _broadcast_local(cls, session_id: str, event: dict[str, Any]) -> None:
        async with cls._lock:
            subscribers = tuple(cls._subscribers.get(session_id, ()))
        stale: list[WebSocket] = []
        for websocket in subscribers:
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await cls.disconnect(session_id, websocket)

    @classmethod
    async def _redis_listener(cls, session_id: str) -> None:
        redis = get_redis()
        pubsub = redis.pubsub()
        channel = cls.CHANNEL_PREFIX + session_id
        try:
            pubsub.subscribe(channel)
            ready = cls._listener_ready.get(session_id)
            if ready:
                ready.set()
            loop = asyncio.get_running_loop()
            while True:
                message = await loop.run_in_executor(None, lambda: pubsub.get_message(timeout=1.0))
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                payload = message.get("data")
                event = json.loads(payload) if isinstance(payload, str) else payload
                if isinstance(event, dict):
                    await cls._broadcast_local(session_id, event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis realtime listener failed for %s: %s", session_id, exc)
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    @classmethod
    async def shutdown(cls) -> None:
        tasks = tuple(cls._listeners.values())
        cls._listeners.clear()
        cls._listener_ready.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
