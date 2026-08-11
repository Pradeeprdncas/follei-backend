"""Worker that crawls a website and fans normalized documents into indexing."""
from __future__ import annotations

import asyncio
import signal
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from loguru import logger

from app.config.database import SessionLocal
from app.config.kafka import ensure_topics, get_consumer, get_producer
from app.config.settings import get_settings
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.routers.upload import UPLOAD_DIR
from app.services.knowledge.crawlers import crawl_with_adapter
from app.services.knowledge.ingestion_retry import IngestionJobFailed, publish_ingestion_retry, record_ingestion_failure
from app.services.knowledge.object_storage import store_source


_settings = get_settings()


def _queue_index(db, *, tenant_id: str, source_id: str, run_id: str, record: dict, category: str | None) -> str:
    job_id = uuid4()
    is_asset = "content" in record
    suffix = record.get("file_type", "txt") if is_asset else "txt"
    path = Path(UPLOAD_DIR) / f"{job_id}.{suffix}"
    if is_asset:
        path.write_bytes(record["content"])
        filename = record.get("filename") or path.name
    else:
        path.write_text(f"# {record['title']}\nSource URL: {record['url']}\n\n{record['text']}", encoding="utf-8")
        filename = f"website-page-{job_id}.txt"
    object_key = store_source(path, tenant_id=tenant_id, job_id=str(job_id))
    payload = {
        "job_id": str(job_id), "tenant_id": tenant_id, "file_path": str(path),
        "filename": filename, "source_uri": record["url"], "uploaded_by": "website_ingestion_worker",
        "file_type": suffix, "category": category, "object_key": object_key,
        "source_metadata": {"knowledge_source_id": source_id, "ingestion_run_id": run_id},
    }
    db.add(IndexingJob(id=job_id, tenant_id=UUID(tenant_id), status="queued", payload=payload))
    get_producer().send(_settings.KAFKA_TOPIC_INDEXING, key=str(job_id), value=payload)
    return str(job_id)


def process_website_job(data: dict) -> None:
    db = SessionLocal()
    job = db.query(SourceIngestionJob).filter(
        SourceIngestionJob.id == UUID(data["job_id"]),
        SourceIngestionJob.tenant_id == UUID(data["tenant_id"]),
    ).first()
    run = db.get(IngestionRun, UUID(data["run_id"]))
    source = db.get(KnowledgeSource, UUID(data["source_id"]))
    if not job or not run or not source or run.tenant_id != job.tenant_id or source.tenant_id != job.tenant_id:
        db.close()
        raise ValueError("Unknown or cross-tenant website ingestion job")
    try:
        job.status = run.status = source.status = "running"
        job.attempt += 1
        job.payload = {**(job.payload or {}), "stage": "starting_crawl"}
        run.started_at = datetime.utcnow()
        db.commit()

        def persist_progress(progress: dict[str, object]) -> None:
            job.payload = {**(job.payload or {}), **progress}
            run.page_count = int(progress.get("pages_discovered") or run.page_count or 0)
            # During crawling this counts discovered downloadable documents;
            # after fan-out it becomes the total page+document indexing count.
            run.document_count = int(progress.get("documents_discovered") or 0)
            db.commit()

        records, selected_engine = asyncio.run(crawl_with_adapter(
            data["url"], engine=data.get("engine", "auto"),
            max_pages=_settings.WEBSITE_CRAWL_PAGE_LIMIT,
            include_assets=True,
            progress_callback=persist_progress,
        ))
        pages = [record for record in records if "content" not in record and record.get("text")]
        assets = [record for record in records if "content" in record]
        if not pages and not assets:
            raise ValueError("No crawlable content was found")
        indexed_jobs = []
        for record in [*pages, *assets]:
            indexed_jobs.append(_queue_index(
                db, tenant_id=data["tenant_id"], source_id=data["source_id"], run_id=data["run_id"],
                record=record, category=None,
            ))
            job.payload = {
                **(job.payload or {}),
                "stage": "queueing_for_classification",
                "items_queued": len(indexed_jobs),
                "pages_discovered": len(pages),
                "documents_discovered": len(assets),
            }
            db.commit()
        get_producer().flush()
        job.payload = {
            **(job.payload or {}),
            "stage": "indexing",
            "selected_engine": selected_engine,
            "indexing_job_ids": indexed_jobs,
            "items_queued": len(indexed_jobs),
            "pages_discovered": len(pages),
            "documents_discovered": len(assets),
        }
        job.status = "completed"
        source.status = "processing"
        run.status = "processing"
        run.page_count = len(pages)
        run.document_count = len(indexed_jobs)
        db.commit()
    except Exception as exc:
        failure = record_ingestion_failure(job, run, exc, max_attempts=_settings.KAFKA_INGESTION_MAX_ATTEMPTS)
        source.status = "retrying" if failure.retryable else "failed"
        if not failure.retryable:
            run.completed_at = datetime.utcnow()
        db.commit()
        raise IngestionJobFailed(failure) from exc
    finally:
        db.close()


class WebsiteIngestionWorker:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *_):
        self.running = False

    def run(self):
        ensure_topics()
        consumer = get_consumer(_settings.KAFKA_TOPIC_WEBSITE_INGESTION, "follei-website-ingestion")
        try:
            for message in consumer:
                if not self.running:
                    break
                try:
                    process_website_job(message.value)
                    consumer.commit()
                except IngestionJobFailed as exc:
                    logger.exception("Website ingestion failed: {}", exc)
                    publish_ingestion_retry(get_producer(), _settings.KAFKA_TOPIC_WEBSITE_INGESTION, message.value, exc.failure)
                    consumer.commit()
                except Exception as exc:
                    logger.exception("Website ingestion worker rejected a message: {}", exc)
                    consumer.commit()
        finally:
            consumer.close()


if __name__ == "__main__":
    WebsiteIngestionWorker().run()
