"""Domain event publisher — single Kafka topic with event type routing.

All events are published to the `domain-events` topic. Each event
has an `event_type` that downstream consumers use to filter.

Event types:
  conversation.created
  conversation.message.added
  conversation.analysis.requested
  conversation.analysis.completed
  lead.score.updated
  crm.sync.requested
"""
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict

from app.config.kafka import get_producer
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()

EVENT_CONVERSATION_CREATED = "conversation.created"
EVENT_CONVERSATION_MESSAGE_ADDED = "conversation.message.added"
EVENT_CONVERSATION_ANALYSIS_REQUESTED = "conversation.analysis.requested"
EVENT_CONVERSATION_ANALYSIS_COMPLETED = "conversation.analysis.completed"
EVENT_LEAD_SCORE_UPDATED = "lead.score.updated"
EVENT_CRM_SYNC_REQUESTED = "crm.sync.requested"


@dataclass
class DomainEvent:
    event_id: str
    event_type: str
    source: str
    tenant_id: str
    timestamp: str
    data: dict
    metadata: dict = field(default_factory=lambda: {"version": 1})

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    def to_kafka_message(self) -> tuple[str | None, str]:
        return (self.event_type, self.to_json())


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
            key, value = event.to_kafka_message()
            producer.send(
                _settings.KAFKA_TOPIC_DOMAIN_EVENTS,
                key=key,
                value=value,
            )
            producer.flush()
            logger.info(f"Event published: {event_type} (tenant={tenant_id})")
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")

    def publish_async(self, event_type: str, tenant_id: str, data: dict) -> None:
        """Publish without flush — higher throughput, no delivery guarantee here."""
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
            key, value = event.to_kafka_message()
            future = producer.send(
                _settings.KAFKA_TOPIC_DOMAIN_EVENTS,
                key=key,
                value=value,
            )
            future.add_callback(lambda _: logger.debug(f"Event ack: {event_type}"))
            future.add_errback(lambda e: logger.error(f"Event nack: {event_type} — {e}"))
        except Exception as e:
            logger.error(f"Failed to publish event async {event_type}: {e}")
