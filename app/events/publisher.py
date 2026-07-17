"""Domain event publisher — standardized publishing across all domains.

Wraps the Kafka producer and provides a unified publish() interface
used by all domain services.
"""
import uuid
from datetime import datetime
from loguru import logger

from app.events.base import DomainEvent
from app.config.kafka import get_producer
from app.config.settings import get_settings

_settings = get_settings()


class DomainEventPublisher:
    """Publishes domain events to the Kafka domain-events topic."""

    def __init__(self, source: str = "backend"):
        self.source = source

    def publish(self, event_type: str, tenant_id: str, data: dict) -> None:
        """Publish an event synchronously."""
        try:
            producer = get_producer()
            event = DomainEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                source=self.source,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                data=data,
            )
            producer.send(
                _settings.KAFKA_TOPIC_DOMAIN_EVENTS,
                key=event.event_type,
                value=event.to_json(),
            )
            producer.flush()
            logger.info(f"Event published: {event_type} (tenant={tenant_id})")
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")

    def publish_async(self, event_type: str, tenant_id: str, data: dict) -> None:
        """Publish without flush — higher throughput, no delivery guarantee."""
        try:
            producer = get_producer()
            event = DomainEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                source=self.source,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                data=data,
            )
            future = producer.send(
                _settings.KAFKA_TOPIC_DOMAIN_EVENTS,
                key=event.event_type,
                value=event.to_json(),
            )
            future.add_callback(lambda _: logger.debug(f"Event ack: {event_type}"))
            future.add_errback(lambda e: logger.error(f"Event nack: {event_type} — {e}"))
        except Exception as e:
            logger.error(f"Failed to publish event async {event_type}: {e}")
