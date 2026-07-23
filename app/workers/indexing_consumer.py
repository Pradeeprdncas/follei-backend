"""Kafka consumer that processes document indexing jobs."""
import sys
import signal
from time import sleep
from datetime import datetime
from kafka import TopicPartition
from kafka.structs import OffsetAndMetadata
from app.config.kafka import get_consumer, get_producer, ensure_topics
from app.config.database import SessionLocal
from app.models.knowledge.indexing_job import IndexingJob
from app.config.settings import get_settings
from app.services.rag.pipelines.indexing import index_document
from app.services.knowledge.object_storage import materialize_source
from loguru import logger

_settings = get_settings()


def failure_destination(attempt_count: int, max_attempts: int) -> tuple[str, str]:
    """Return persisted job status and Kafka destination for a failed attempt."""
    if attempt_count >= max_attempts:
        return "dead_lettered", _settings.KAFKA_TOPIC_INDEXING_DLQ
    return "retrying", _settings.KAFKA_TOPIC_INDEXING


def commit_message(consumer, message) -> None:
    consumer.commit({
        TopicPartition(message.topic, message.partition): OffsetAndMetadata(message.offset + 1, None)
    })


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
                logger.info(f"Received indexing job: {data.get('job_id')}")
                db = SessionLocal()
                job = db.query(IndexingJob).filter(IndexingJob.id == data.get("job_id"), IndexingJob.tenant_id == data.get("tenant_id")).first()
                if job:
                    job.status = "processing"
                    job.attempt_count = int(job.attempt_count or 0) + 1
                    job.started_at = datetime.utcnow()
                    job.last_error = None
                    db.commit()

                try:
                    import asyncio
                    with materialize_source(data) as source_path:
                        result = asyncio.run(index_document(
                            file_path=str(source_path),
                            tenant_id=data["tenant_id"],
                            source_uri=data.get("source_uri"),
                            original_filename=data.get("filename"),
                            uploaded_by=data.get("uploaded_by"),
                            category_override=data.get("category"),
                            workspace_id=data.get("workspace_id"),
                            processing_instructions=data.get("processing_instructions"),
                            source_metadata=data.get("source_metadata"),
                            return_details=True,
                        ))
                    if job:
                        job.document_id = result["document_id"]
                        job.disposition = result["disposition"]
                        job.status = "indexed"
                        job.completed_at = datetime.utcnow()
                        db.commit()
                    logger.info(f"Successfully indexed document {data['job_id']}")
                    commit_message(consumer, message)
                except Exception as e:
                    attempts = int(job.attempt_count or 1) if job else int(data.get("retry_count", 0)) + 1
                    job_status, destination = failure_destination(attempts, _settings.KAFKA_INDEXING_MAX_ATTEMPTS)
                    if job:
                        job.status = job_status
                        job.last_error = str(e)[:4000]
                        db.commit()
                    failed_message = {**data, "retry_count": attempts, "last_error": str(e)[:1000]}
                    try:
                        producer = get_producer()
                        producer.send(destination, key=str(data.get("job_id") or ""), value=failed_message)
                        producer.flush()
                    except Exception:
                        logger.exception("Could not publish indexing retry/dead-letter message; leaving offset uncommitted")
                        raise
                    commit_message(consumer, message)
                    logger.error(f"Failed to index document {data.get('job_id')} attempt={attempts} status={job_status}: {e}")
                finally:
                    db.close()

        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            consumer.close()
            logger.info("Indexing worker stopped")


if __name__ == "__main__":
    worker = IndexingWorker()
    while worker.running:
        try:
            worker.run()
        except Exception as exc:
            logger.exception(f"Indexing worker supervisor restarting after error: {exc}")
        if worker.running:
            sleep(2.0)


