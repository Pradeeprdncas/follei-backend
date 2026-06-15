"""Kafka consumer that processes document indexing jobs."""
import sys
import signal
from app.config.kafka import get_consumer, ensure_topics
from app.config.settings import get_settings
from app.services.rag.pipelines.indexing import index_document
from loguru import logger

_settings = get_settings()


class IndexingWorker:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received, stopping worker...")
        self.running = False

    def run(self):
        """Main consumer loop."""
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_INDEXING, _settings.KAFKA_CONSUMER_GROUP)
        logger.info(f"Indexing worker started. Listening on topic: {_settings.KAFKA_TOPIC_INDEXING}")

        try:
            for message in consumer:
                if not self.running:
                    break

                data = message.value
                logger.info(f"Received indexing job: {data.get('document_id')}")

                try:
                    import asyncio
                    asyncio.run(index_document(
                        file_path=data["file_path"],
                        tenant_id=data["tenant_id"],
                    ))
                    logger.info(f"Successfully indexed document {data['document_id']}")
                except Exception as e:
                    logger.error(f"Failed to index document {data.get('document_id')}: {e}")
                    # Message will be retried based on Kafka config

        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            consumer.close()
            logger.info("Indexing worker stopped")


if __name__ == "__main__":
    worker = IndexingWorker()
    worker.run()
