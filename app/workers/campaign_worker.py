"""Campaign worker — processes campaign.launched events, sends messages."""
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


class CampaignWorker:
    """Consumes campaign.launched events and orchestrates message delivery."""

    def __init__(self):
        self.running = True

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_DOMAIN_EVENTS, "follei-campaign-group")
        logger.info("Campaign worker started")
        try:
            while self.running:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        self._process(msg)
        except KeyboardInterrupt:
            logger.info("Shutting down campaign worker")
        finally:
            consumer.close()

    def _process(self, message) -> None:
        pass  # TODO: Implement campaign execution

    def _shutdown(self, signum=None, frame=None):
        self.running = False
