"""Four-resource Google Workspace incremental synchronization worker."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from kafka.errors import CommitFailedError
from loguru import logger

from app.config.database import SessionLocal
from app.config.kafka import ensure_topics, get_consumer, get_producer
from app.config.settings import get_settings
from app.models.integrations.oauth_connection import GoogleWorkspaceConnection
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.services.integrations.google_workspace import GoogleWorkspaceOAuthService
from app.services.knowledge.object_storage import store_source
from app.services.knowledge.ingestion_retry import IngestionJobFailed, publish_ingestion_retry, record_ingestion_failure
from app.services.knowledge.run_status import reconcile_ingestion_run


_settings = get_settings()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
RESOURCE_CATEGORY = {"gmail": "communication_preferences", "drive": "general", "calendar": "follow_up_patterns", "contacts": "contact_company_information"}
INDEX_RECORD_BATCH_SIZE = 50


async def process_google_job(data: dict) -> None:
    db = SessionLocal()
    job = db.query(SourceIngestionJob).filter(SourceIngestionJob.id == UUID(data["job_id"]), SourceIngestionJob.tenant_id == UUID(data["tenant_id"])).first()
    run = db.query(IngestionRun).filter(IngestionRun.id == UUID(data["run_id"]), IngestionRun.tenant_id == UUID(data["tenant_id"])).first()
    connection = db.query(GoogleWorkspaceConnection).filter(GoogleWorkspaceConnection.id == UUID(data["connection_id"]), GoogleWorkspaceConnection.tenant_id == UUID(data["tenant_id"])).first()
    if not job or not run or not connection:
        db.close()
        raise ValueError("Unknown or cross-tenant Google sync job")
    # Kafka is at-least-once. A process interruption can leave an older copy
    # of the message in the topic; never repeat completed/dead-lettered work or
    # consume attempts beyond the configured retry budget.
    if job.status in {"completed", "dead_lettered"}:
        db.close()
        return
    if int(job.attempt or 0) >= _settings.KAFKA_INGESTION_MAX_ATTEMPTS:
        job.status = "dead_lettered"
        job.last_error = job.last_error or "Retry budget exhausted after worker interruption"
        db.commit()
        reconcile_ingestion_run(db, run)
        db.close()
        return
    resource = data["resource"]
    try:
        job.status = "running"; job.attempt += 1; run.status = "running"
        job.payload = {**(job.payload or {}), "stage": "fetching", "resource": resource, "record_count": 0}
        db.commit()
        service = GoogleWorkspaceOAuthService()
        token = await service.valid_access_token(db, connection)
        cursors = dict(connection.sync_cursors or {})
        records, cursor = await service.fetch_resource(token, resource, cursor=cursors.get(resource))
        job.payload = {**(job.payload or {}), "stage": "queueing_for_classification", "record_count": len(records)}
        db.commit()
        record_batches = [records[index:index + INDEX_RECORD_BATCH_SIZE] for index in range(0, len(records), INDEX_RECORD_BATCH_SIZE)] or [[]]
        producer = get_producer()
        indexing_ids: list[str] = []
        for batch_number, batch_records in enumerate(record_batches, start=1):
            path = Path(UPLOAD_DIR) / f"google-{job.id}-{batch_number}.json"
            path.write_text(json.dumps({"resource": resource, "records": batch_records}, ensure_ascii=False), encoding="utf-8")
            index_id = uuid4()
            object_key = store_source(path, tenant_id=data["tenant_id"], job_id=str(index_id))
            payload = {
                "job_id": str(index_id), "tenant_id": data["tenant_id"], "file_path": str(path),
                "filename": path.name, "source_uri": f"google-workspace://{connection.provider_account_id}/{resource}/batch/{batch_number}",
                "uploaded_by": "google_workspace_worker", "file_type": "json",
                "category": RESOURCE_CATEGORY[resource], "object_key": object_key,
                "source_metadata": {"knowledge_source_id": data["source_id"], "ingestion_run_id": data["run_id"], "resource": resource, "batch_number": batch_number, "batch_count": len(record_batches)},
            }
            db.add(IndexingJob(id=index_id, tenant_id=connection.tenant_id, status="queued", payload=payload))
            producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(index_id), value=payload)
            indexing_ids.append(str(index_id))
        producer.flush()
        cursors[resource] = cursor
        connection.sync_cursors = cursors
        connection.last_synced_at = datetime.utcnow()
        connection.last_error = None
        job.status = "completed"
        job.payload = {
            **(job.payload or {}),
            "stage": "indexing",
            "record_count": len(records),
            "items_queued": len(indexing_ids),
            "indexing_job_ids": indexing_ids,
        }
        run.document_count = sum(item.status == "completed" for item in db.query(SourceIngestionJob).filter(SourceIngestionJob.run_id == run.id).all())
        db.commit()
        reconcile_ingestion_run(db, run)
    except Exception as exc:
        failure = record_ingestion_failure(
            job, run, exc,
            max_attempts=_settings.KAFKA_INGESTION_MAX_ATTEMPTS,
            terminal_run_status="partial",
        )
        connection.last_error = failure.error
        db.commit()
        reconcile_ingestion_run(db, run)
        raise IngestionJobFailed(failure) from exc
    finally:
        db.close()


class GoogleWorkspaceWorker:
    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC, "follei-google-workspace")
        try:
            for message in consumer:
                try:
                    asyncio.run(process_google_job(message.value))
                except IngestionJobFailed as exc:
                    publish_ingestion_retry(get_producer(), _settings.KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC, message.value, exc.failure)
                finally:
                    try:
                        consumer.commit()
                    except CommitFailedError:
                        # The durable job row and idempotent terminal-state
                        # guard make replay safe. A group rebalance must not
                        # terminate the worker after a long Google download.
                        logger.warning(
                            "Google Workspace Kafka offset commit was lost to a rebalance; "
                            "the durable job may be replayed safely"
                        )
        finally:
            consumer.close()


if __name__ == "__main__":
    GoogleWorkspaceWorker().run()
