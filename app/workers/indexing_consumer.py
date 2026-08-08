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
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun
from app.models.leads.lead import Lead
from app.config.ferretdb import get_context_database
from app.config.settings import get_settings
from app.services.rag.pipelines.indexing import index_document
from app.services.knowledge.object_storage import materialize_source
from app.services.knowledge.category_summaries import refresh_category_summaries
from loguru import logger

_settings = get_settings()


def sync_ingestion_run_status(db, job: IndexingJob) -> None:
    """Finish a source run only after every fanned-out index job is terminal."""
    metadata = (job.payload or {}).get("source_metadata") or {}
    run_id = metadata.get("ingestion_run_id")
    source_id = metadata.get("knowledge_source_id")
    if not run_id or not source_id:
        return
    related = [
        row for row in db.query(IndexingJob).filter(IndexingJob.tenant_id == job.tenant_id).all()
        if str(((row.payload or {}).get("source_metadata") or {}).get("ingestion_run_id") or "") == str(run_id)
    ]
    if not related:
        return
    statuses = {str(row.status or "").lower() for row in related}
    terminal_success = {"indexed", "completed", "ready"}
    terminal_failure = {"failed", "dead_lettered", "dead_letter", "error"}
    if any(value not in terminal_success | terminal_failure for value in statuses):
        return
    run = db.query(IngestionRun).filter(
        IngestionRun.id == UUID(str(run_id)), IngestionRun.tenant_id == job.tenant_id,
    ).first()
    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.id == UUID(str(source_id)), KnowledgeSource.tenant_id == job.tenant_id,
    ).first()
    if not run or not source:
        return
    failed = any(value in terminal_failure for value in statuses)
    run.status = "partial" if failed and any(value in terminal_success for value in statuses) else "failed" if failed else "completed"
    source.status = "needs_attention" if failed else "active"
    run.completed_at = datetime.utcnow()
    run.error = "One or more indexing jobs failed" if failed else None
    db.commit()


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


