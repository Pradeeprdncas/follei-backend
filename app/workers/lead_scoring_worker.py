"""Lead scoring worker — processes lead.score.* events and updates lead temperatures."""
from app.events.base import EVENT_LEAD_SCORE_UPDATED, EVENT_LEAD_TEMPERATURE_CHANGED
from app.events.publisher import DomainEventPublisher
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class LeadScoringWorker:
    """Consumes lead.score.updated events and recalculates temperatures."""

    def __init__(self):
        self.running = True
        self.event_publisher = DomainEventPublisher(source="lead_scoring.worker")

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-lead-scoring-group")
        logger.info("Lead scoring worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                if not records:
                    continue
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down lead scoring worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement lead scoring logic

    def _shutdown(self, signum=None, frame=None):
        self.running = False
