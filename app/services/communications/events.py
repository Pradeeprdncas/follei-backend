"""Communications domain event helpers."""
from loguru import logger
from app.events.publisher import DomainEventPublisher


_publisher = DomainEventPublisher(source="communications")


def publish_event(event_type: str, tenant_id: str, data: dict) -> None:
    try:
        _publisher.publish(event_type, tenant_id or "unknown", data)
    except Exception as e:
        logger.warning(f"Failed to publish event {event_type}: {e}")


def publish_event_async(event_type: str, tenant_id: str, data: dict) -> None:
    try:
        _publisher.publish_async(event_type, tenant_id or "unknown", data)
    except Exception as e:
        logger.warning(f"Failed to publish async event {event_type}: {e}")
