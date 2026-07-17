"""Communication worker — handles outbound messages across all channels."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class CommunicationWorker:
    """Consumes conversation.message.* events and delivers via appropriate channel provider."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-communication-group")
        logger.info("Communication worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down communication worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement channel delivery

    def _shutdown(self, signum=None, frame=None):
        self.running = False
