"""Kafka consumer that processes document indexing jobs."""
import sys
import signal
from time import sleep
from datetime import datetime
from uuid import UUID
from kafka import TopicPartition
from kafka.structs import OffsetAndMetadata
from app.config.kafka import get_consumer, get_producer, ensure_topics
from app.config.database import SessionLocal
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.ingestion import IngestionRun
from app.models.leads.lead import Lead
from app.config.ferretdb import get_context_database
from app.config.settings import get_settings
from app.services.rag.pipelines.indexing import index_document
from app.services.knowledge.object_storage import materialize_source
from app.services.knowledge.category_summaries import refresh_category_summaries
from app.services.knowledge.run_status import reconcile_ingestion_run
from loguru import logger

_settings = get_settings()

_TERMINAL_JOB_STATUSES = {"indexed", "completed", "ready", "failed", "dead_lettered", "dead_letter", "error"}


def replay_durable_indexing_jobs() -> int:
    """Republish durable jobs that were committed but never reached Kafka.

    PostgreSQL is the source of truth for indexing work.  A process can stop
    after committing a job row but before publishing its Kafka message, so the
    worker replays non-terminal rows on startup.  The consumer separately
    ignores terminal duplicates, making this safe if Kafka already contains a
    copy of the message.
    """
    db = SessionLocal()
    try:
        jobs = db.query(IndexingJob).filter(IndexingJob.status.in_(("queued", "retrying"))).all()
        if not jobs:
            return 0
        producer = get_producer()
        published = 0
        for job in jobs:
            payload = dict(job.payload or {})
            payload["job_id"] = str(job.id)
            payload["tenant_id"] = str(job.tenant_id)
            payload["retry_count"] = int(job.attempt_count or 0)
            producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(job.id), value=payload)
            published += 1
        producer.flush()
        logger.info("Replayed {} durable indexing job(s) to Kafka", published)
        return published
    finally:
        db.close()


def sync_ingestion_run_status(db, job: IndexingJob) -> None:
    """Finish a source run only after every fanned-out index job is terminal."""
    metadata = (job.payload or {}).get("source_metadata") or {}
    run_id = metadata.get("ingestion_run_id")
    source_id = metadata.get("knowledge_source_id")
    if not run_id or not source_id:
        return
    run = db.query(IngestionRun).filter(
        IngestionRun.id == UUID(str(run_id)), IngestionRun.tenant_id == job.tenant_id,
    ).first()
    if not run:
        return
    reconcile_ingestion_run(db, run)


def sync_lead_pre_nurturing_status(db, job: IndexingJob) -> None:
    """Mirror the terminal System 1 crawl state to PostgreSQL and FerretDB."""
    payload = job.payload or {}
    import_job_id = str(payload.get("lead_import_job_id") or "")
    if not import_job_id:
        return
    related = [
        row
        for row in db.query(IndexingJob).filter(IndexingJob.tenant_id == job.tenant_id).all()
        if str((row.payload or {}).get("lead_import_job_id") or "") == import_job_id
    ]
    if not related:
        return
    terminal_ok = {"indexed", "completed", "ready"}
    terminal_failed = {"failed", "dead_lettered", "dead_letter", "error"}
    statuses = [str(row.status or "").lower() for row in related]
    if any(status not in terminal_ok | terminal_failed for status in statuses):
        stage = "processing"
    elif any(status in terminal_failed for status in statuses):
        stage = "needs_attention"
    else:
        # FerretDB projection is delivered asynchronously through the outbox.
        # The verification API promotes this to knowledge_ready only after it
        # can observe that projection.
        stage = "indexing_complete"
    lead_ids = sorted({
        str(value)
        for row in related
        for value in (row.payload or {}).get("lead_ids", [])
    })
    state = {
        "system": "System 1",
        "stage": stage,
        "import_job_id": import_job_id,
        "crawl_jobs": [str(row.id) for row in related],
        "indexed_jobs": sum(status in terminal_ok for status in statuses),
        "failed_jobs": sum(status in terminal_failed for status in statuses),
    }
    lead_uuids = [UUID(value) for value in lead_ids]
    leads = (
        db.query(Lead).filter(
            Lead.tenant_id == job.tenant_id,
            Lead.id.in_(lead_uuids),
        ).all()
        if lead_uuids
        else []
    )
    for lead in leads:
        lead.profile_data = {**(lead.profile_data or {}), "pre_nurturing": state}
    db.commit()
    try:
        memory = get_context_database()
        for lead_id in lead_ids:
            for collection_name, key in (
                ("lead_import_memory", {"tenant_id": str(job.tenant_id), "lead_id": lead_id}),
                (
                    "tenant_context",
                    {
                        "tenant_id": str(job.tenant_id),
                        "subject_type": "lead",
                        "subject_id": lead_id,
                    },
                ),
            ):
                memory[collection_name].update_one(key, {"$set": {"pre_nurturing": state}}, upsert=True)
    except Exception as exc:
        logger.warning("System 1 completion status was saved to PostgreSQL but not FerretDB: {}", exc)


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
        replay_durable_indexing_jobs()
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
                if job and str(job.status or "").lower() in _TERMINAL_JOB_STATUSES:
                    logger.info("Skipping duplicate terminal indexing job {} ({})", job.id, job.status)
                    commit_message(consumer, message)
                    db.close()
                    continue
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
                        refresh_category_summaries(db, job.tenant_id)
                        sync_ingestion_run_status(db, job)
                        sync_lead_pre_nurturing_status(db, job)
                    logger.info(f"Successfully indexed document {data['job_id']}")
                    commit_message(consumer, message)
                except Exception as e:
                    attempts = int(job.attempt_count or 1) if job else int(data.get("retry_count", 0)) + 1
                    job_status, destination = failure_destination(attempts, _settings.KAFKA_INDEXING_MAX_ATTEMPTS)
                    if job:
                        job.status = job_status
                        job.last_error = str(e)[:4000]
                        db.commit()
                        sync_ingestion_run_status(db, job)
                        sync_lead_pre_nurturing_status(db, job)
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


