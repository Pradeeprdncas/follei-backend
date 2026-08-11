"""Reconcile one ingestion run across source-fetch and indexing fan-out jobs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob


_SOURCE_SUCCESS = {"completed"}
_SOURCE_FAILURE = {"failed"}
_INDEX_SUCCESS = {"indexed", "completed", "ready"}
_INDEX_FAILURE = {"failed", "dead_lettered", "dead_letter", "error"}


def reconcile_ingestion_run(db: Session, run: IngestionRun) -> None:
    """Persist a run status only after every current fan-out layer agrees."""
    source_jobs = db.query(SourceIngestionJob).filter(
        SourceIngestionJob.run_id == run.id,
        SourceIngestionJob.tenant_id == run.tenant_id,
    ).all()
    source_statuses = {str(job.status or "").lower() for job in source_jobs}
    if "retrying" in source_statuses:
        run.status = "retrying"
        run.completed_at = None
        db.commit()
        return
    if any(status not in _SOURCE_SUCCESS | _SOURCE_FAILURE for status in source_statuses):
        run.status = "running"
        run.completed_at = None
        db.commit()
        return

    indexing_jobs = db.query(IndexingJob).filter(
        IndexingJob.tenant_id == run.tenant_id,
        IndexingJob.payload["source_metadata"]["ingestion_run_id"].as_string() == str(run.id),
    ).all()
    index_statuses = {str(job.status or "").lower() for job in indexing_jobs}
    source_success = any(status in _SOURCE_SUCCESS for status in source_statuses)
    expected_indexing_jobs = sum(
        int((job.payload or {}).get("items_queued") or 0)
        for job in source_jobs
        if str(job.status or "").lower() in _SOURCE_SUCCESS
    )
    if source_success and (
        not indexing_jobs
        or len(indexing_jobs) < expected_indexing_jobs
        or any(status not in _INDEX_SUCCESS | _INDEX_FAILURE for status in index_statuses)
    ):
        run.status = "processing"
        run.completed_at = None
        db.commit()
        return

    failed = any(status in _SOURCE_FAILURE for status in source_statuses) or any(
        status in _INDEX_FAILURE for status in index_statuses
    )
    succeeded = any(status in _INDEX_SUCCESS for status in index_statuses)
    run.status = "partial" if failed and succeeded else "failed" if failed else "completed"
    run.completed_at = datetime.utcnow()
    if failed and not run.error:
        run.error = "One or more ingestion jobs failed"

    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.id == run.source_id,
        KnowledgeSource.tenant_id == run.tenant_id,
    ).first()
    if source is not None:
        source.status = "needs_attention" if failed else "active"
    db.commit()
