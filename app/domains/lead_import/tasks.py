"""Background Celery tasks for lead import processing with progress tracking."""
import time
import asyncio
from uuid import UUID
from loguru import logger
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.domains.lead_import.celery_app import celery_app
from app.domains.lead_import.repository import LeadImportRepository
from app.domains.lead_import.service import LeadImportService
from app.domains.lead_import.constants import ImportStatus


def _update_progress(job_id: UUID, repo: LeadImportRepository, pct: float, stage: str, eta: float | None = None):
    job = repo.get_job(job_id)
    if not job:
        return
    stats = dict(job.statistics or {})
    stats["progress"] = {"percentage": round(pct, 1), "stage": stage, "eta_seconds": eta}
    job.statistics = stats
    repo.db.flush()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_import_task(self, job_id_str: str, tenant_id_str: str, filename: str, file_type: str, file_path: str):
    """Run the full lead import pipeline with progress tracking."""
    job_id = UUID(job_id_str)
    tenant_id = UUID(tenant_id_str)
    db: Session = SessionLocal()
    try:
        repo = LeadImportRepository(db)
        svc = LeadImportService(repo)
        total_stages = 9  # parse, extract, enrich, intelligence, correct, validate, dedup, review, finalize
        stage_weights = [0.10, 0.20, 0.10, 0.10, 0.05, 0.10, 0.15, 0.10, 0.10]
        start = time.time()

        def progress(stage_idx: int, sub_pct: float = 1.0):
            base = sum(stage_weights[:stage_idx])
            pct = (base + stage_weights[stage_idx] * sub_pct) * 100
            elapsed = time.time() - start
            remaining = (elapsed / max(pct, 1)) * (100 - pct) if pct > 0 else 0
            _update_progress(job_id, repo, pct, svc.STAGE_NAMES.get(stage_idx, "processing"), round(remaining, 1))
            repo.db.commit()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            progress(0, 0)
            loop.run_until_complete(svc.process_upload(
                tenant_id=tenant_id,
                filename=filename,
                file_type=file_type,
                file_path=file_path,
                uploaded_by=None,
                progress_callback=progress,
            ))
        finally:
            loop.close()

        progress(len(stage_weights) - 1, 1.0)
        logger.info("Import job {} completed successfully", job_id)
    except Exception as exc:
        logger.exception("Import job {} failed: {}", job_id, exc)
        try:
            repo = LeadImportRepository(db)
            repo.update_job_status(job_id, ImportStatus.FAILED, error_message=str(exc))
            db.commit()
        except Exception:
            db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()
