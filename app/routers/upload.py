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
from app.models.knowledge.document import Document, DocumentChunk, DocumentSection
from app.models.knowledge.entity import Entity
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.config.ferretdb import get_context_database
from app.config.qdrant import get_qdrant
from qdrant_client.models import FieldCondition, Filter, MatchValue
from app.services.knowledge.object_storage import store_source, source_available
from app.services.knowledge.categories import KnowledgeCategory, normalize_category
from loguru import logger

router = APIRouter(prefix="/upload", tags=["upload"])
_settings = get_settings()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".ppt", ".pptx", ".eml", ".msg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
TARGET_CATEGORIES = {item.value for item in KnowledgeCategory}


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    source_uri: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    primary_category: KnowledgeCategory | None = Form(None, description="User-selected primary knowledge category"),
    category: str | None = Form(None, description="Deprecated alias for primary_category"),
    workspace_id: UUID | None = Form(None),
    processing_instructions: str | None = Form(None, max_length=4000),
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
    try:
        normalized_category = normalize_category(primary_category.value if primary_category else category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        "workspace_id": str(workspace_id) if workspace_id else None,
        "processing_instructions": processing_instructions.strip() if processing_instructions else None,
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

    return {"job_id": job_id, "document_id": None, "tenant_id": tenant_id, "filename": file.filename, "source_uri": canonical_uri, "primary_category": normalized_category, "target_category": normalized_category, "workspace_id": str(workspace_id) if workspace_id else None, "status": "queued", "disposition": "pending", "message": "File uploaded and queued for idempotent indexing"}


def _job_response(job: IndexingJob) -> dict:
    return {"job_id": str(job.id), "tenant_id": str(job.tenant_id), "document_id": str(job.document_id) if job.document_id else None, "status": job.status, "disposition": job.disposition or "pending", "attempt_count": job.attempt_count, "last_error": job.last_error, "created_at": job.created_at, "started_at": job.started_at, "completed_at": job.completed_at, "payload": job.payload}


def _document_or_404(db: Session, document_id: UUID, tenant_id: str) -> Document:
    document = db.query(Document).filter(Document.id == document_id, Document.tenant_id == UUID(tenant_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found for tenant")
    return document


@router.get("/documents/{document_id}/status")
def document_processing_status(document_id: UUID, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    document = _document_or_404(db, document_id, authenticated_tenant_id)
    job = db.query(IndexingJob).filter(IndexingJob.tenant_id == document.tenant_id, IndexingJob.document_id == document.id).order_by(IndexingJob.created_at.desc()).first()
    return {"document_id": str(document.id), "status": document.status, "primary_category": document.primary_category or document.category, "minio": {"object_key": (job.payload or {}).get("object_key") if job else None, "status": "stored" if job and (job.payload or {}).get("object_key") else "local_or_unavailable"}, "processing": {"job_status": job.status if job else "unknown", "parsing": "completed" if document.status == "indexed" else document.status, "chunking": "completed" if document.status == "indexed" else "pending", "extraction": "review_ready" if db.query(BusinessFactDraft.id).filter(BusinessFactDraft.document_id == document.id).first() else "pending"}, "sync": {"qdrant": "pending_or_completed", "ferretdb": "pending_or_completed"}}


@router.get("/documents/{document_id}/extraction")
def document_extraction(document_id: UUID, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    document = _document_or_404(db, document_id, authenticated_tenant_id)
    sections = db.query(DocumentSection).filter(DocumentSection.document_id == document.id, DocumentSection.tenant_id == document.tenant_id).order_by(DocumentSection.section_order).all()
    entities = db.query(Entity).filter(Entity.document_id == document.id, Entity.tenant_id == document.tenant_id).all()
    facts = db.query(BusinessFactDraft).filter(BusinessFactDraft.document_id == document.id, BusinessFactDraft.tenant_id == document.tenant_id).all()
    return {"document_id": str(document.id), "primary_category": document.primary_category or document.category, "secondary_categories": document.secondary_categories or [], "sections": [{"section_id": str(row.id), "order": row.section_order, "title": row.title, "category": row.category, "section_type": row.section_type, "page_start": row.page_start, "page_end": row.page_end, "summary": row.summary} for row in sections], "entities": [{"entity_id": str(row.id), "entity_type": row.entity_type, "entity_name": row.name, "category": row.category, "schema_key": row.schema_key, "data": row.data, "status": row.status} for row in entities], "facts": [{"fact_id": str(row.id), "fact_type": row.fact_type, "payload": row.payload, "citation": row.citation, "approval_status": row.approval_status} for row in facts], "warnings": []}


@router.get("/documents/{document_id}/storage-verification")
def document_storage_verification(document_id: UUID, db: Session = Depends(get_db), authenticated_tenant_id: str = Depends(get_authenticated_tenant_id)):
    document = _document_or_404(db, document_id, authenticated_tenant_id)
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
    sections = db.query(DocumentSection).filter(DocumentSection.document_id == document.id).count()
    entities = db.query(Entity).filter(Entity.document_id == document.id).count()
    facts = db.query(BusinessFactDraft).filter(BusinessFactDraft.document_id == document.id).count()
    warning: list[str] = []
    try:
        points, _ = get_qdrant().scroll(collection_name=_settings.QDRANT_COLLECTION_NAME, scroll_filter=Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=authenticated_tenant_id)), FieldCondition(key="document_id", match=MatchValue(value=str(document.id)))]), limit=max(chunks, 1), with_payload=False, with_vectors=False)
        point_count = len(points)
    except Exception as exc:
        point_count = 0; warning.append(f"qdrant: {type(exc).__name__}")
    try:
        context = get_context_database()
        document_view = context["knowledge_document_views"].find_one({"tenant_id": authenticated_tenant_id, "document_id": str(document.id)}, {"_id": 0})
        entity_count = context["knowledge_entities"].count_documents({"tenant_id": authenticated_tenant_id, "document_id": str(document.id)})
    except Exception as exc:
        document_view = None; entity_count = 0; warning.append(f"ferretdb: {type(exc).__name__}")
    consistent = chunks == point_count and (document_view is not None)
    return {"postgres": {"document_exists": True, "section_count": sections, "chunk_count": chunks, "entity_count": entities, "fact_count": facts}, "qdrant": {"indexed": point_count == chunks, "point_count": point_count}, "ferretdb": {"projected": document_view is not None, "document_view_exists": document_view is not None, "entity_projection_count": entity_count}, "minio": {"original_exists": bool(document.path)}, "consistent": consistent, "warnings": warning}


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
