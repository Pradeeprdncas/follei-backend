"""Upload endpoint: persist a source and queue canonical indexing metadata."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from uuid import UUID
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import uuid
from app.config.settings import get_settings
from app.config.kafka import get_producer, ensure_topics
from app.services.rag.document_identity import stable_upload_uri
from app.core.security import get_authenticated_tenant_id, require_matching_tenant
from app.config.database import get_db
from app.models.knowledge.indexing_job import IndexingJob
from app.services.knowledge.object_storage import store_source, source_available
from loguru import logger

router = APIRouter(prefix="/upload", tags=["upload"])
_settings = get_settings()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".ppt", ".pptx", ".eml", ".msg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
TARGET_CATEGORIES = {
    "product", "service", "pricing", "plan", "policy", "sla", "faq", "competitor",
    "customer_segment", "sales_process", "support_process", "payment_process",
    "call_transcript", "knowledge_article",
}


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    source_uri: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    category: str | None = Form(None, description="Optional business category or vector-document kind this upload is intended to populate"),
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Save a source and queue its idempotent versioned indexing job."""
    require_matching_tenant(tenant_id, authenticated_tenant_id)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext or '(none)'}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")
    normalized_category = category.strip().lower() if category else None
    if normalized_category and normalized_category not in TARGET_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown target category '{category}'")
    job_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{job_id}{ext}"
    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.error(f"File save failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    canonical_uri = source_uri or stable_upload_uri(tenant_id, file.filename)
    try:
        object_key = store_source(save_path, tenant_id=tenant_id, job_id=job_id)
    except Exception as exc:
        logger.error(f"Durable object storage failed: {exc}")
        raise HTTPException(status_code=503, detail="Upload was saved locally but durable object storage is unavailable") from exc
    message = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "file_path": str(save_path),
        "filename": file.filename,
        "source_uri": canonical_uri,
        "uploaded_by": uploaded_by,
        "file_type": ext.lstrip(".").lower(),
        "category": normalized_category,
        "object_key": object_key,
    }
    job = IndexingJob(id=UUID(job_id), tenant_id=UUID(tenant_id), status="queued", payload=message)
    db.add(job)
    db.commit()
    try:
        ensure_topics()
        producer = get_producer()
        producer.send(_settings.KAFKA_TOPIC_INDEXING, key=job_id, value=message)
        producer.flush()
        logger.info(f"Queued indexing job {job_id} source={canonical_uri}")
    except Exception as exc:
        job.status = "failed"
        job.last_error = f"queue: {exc}"[:4000]
        db.commit()
        logger.error(f"Kafka enqueue failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Upload was saved but indexing could not be queued; retry after the indexing service is available.",
        ) from exc

    return {"job_id": job_id, "document_id": None, "tenant_id": tenant_id, "filename": file.filename, "source_uri": canonical_uri, "target_category": normalized_category, "status": "queued", "disposition": "pending", "message": "File uploaded and queued for idempotent indexing"}


def _job_response(job: IndexingJob) -> dict:
    return {"job_id": str(job.id), "tenant_id": str(job.tenant_id), "document_id": str(job.document_id) if job.document_id else None, "status": job.status, "disposition": job.disposition or "pending", "attempt_count": job.attempt_count, "last_error": job.last_error, "created_at": job.created_at, "started_at": job.started_at, "completed_at": job.completed_at, "payload": job.payload}


@router.get("/jobs/{job_id}")
def get_indexing_job(job_id: UUID, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    job = db.query(IndexingJob).filter(IndexingJob.id == job_id, IndexingJob.tenant_id == UUID(authenticated_tenant_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Indexing job not found for tenant")
    return _job_response(job)


@router.post("/jobs/{job_id}/retry")
def retry_indexing_job(job_id: UUID, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    job = db.query(IndexingJob).filter(IndexingJob.id == job_id, IndexingJob.tenant_id == UUID(authenticated_tenant_id)).with_for_update().first()
    if not job:
        raise HTTPException(status_code=404, detail="Indexing job not found for tenant")
    if job.status not in {"failed", "retrying", "dead_lettered"}:
        raise HTTPException(status_code=409, detail=f"Only failed jobs can be retried; current status is {job.status}")
    payload = dict(job.payload or {})
    if not source_available(payload):
        raise HTTPException(status_code=410, detail="Original upload is no longer available")
    try:
        ensure_topics()
        producer = get_producer()
        producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(job.id), value=payload)
        producer.flush()
    except Exception as exc:
        job.last_error = f"queue: {exc}"[:4000]
        db.commit()
        raise HTTPException(status_code=503, detail="Indexing retry could not be queued") from exc
    job.status = "queued"
    job.last_error = None
    db.commit()
    db.refresh(job)
    return _job_response(job)
