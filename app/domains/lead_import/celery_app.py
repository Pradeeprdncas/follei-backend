"""Celery app for lead import background processing."""
from celery import Celery
from app.config.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "lead_import",
    broker=_settings.REDIS_URL or "redis://localhost:6379/0",
    backend=_settings.REDIS_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
