"""Analytics worker — aggregates metrics from domain events."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class AnalyticsWorker:
    """Consumes all domain events, aggregates metrics for dashboards."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-analytics-group")
        logger.info("Analytics worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down analytics worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement metric aggregation

    def _shutdown(self, signum=None, frame=None):
        self.running = False
