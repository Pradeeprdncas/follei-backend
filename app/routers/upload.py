"""Upload endpoint: persist a source and queue canonical indexing metadata."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pathlib import Path
import shutil
import uuid
from app.config.settings import get_settings
from app.config.kafka import get_producer, ensure_topics
from app.services.rag.document_identity import stable_upload_uri
from app.core.security import get_authenticated_tenant_id, require_matching_tenant
from loguru import logger

router = APIRouter(prefix="/upload", tags=["upload"])
_settings = get_settings()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    source_uri: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Save a source and queue its idempotent versioned indexing job."""
    require_matching_tenant(tenant_id, authenticated_tenant_id)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    job_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    save_path = UPLOAD_DIR / f"{job_id}{ext}"
    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.error(f"File save failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    canonical_uri = source_uri or stable_upload_uri(tenant_id, file.filename)
    message = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "file_path": str(save_path),
        "filename": file.filename,
        "source_uri": canonical_uri,
        "uploaded_by": uploaded_by,
        "file_type": ext.lstrip(".").lower(),
    }
    try:
        ensure_topics()
        producer = get_producer()
        producer.send(_settings.KAFKA_TOPIC_INDEXING, key=job_id, value=message)
        producer.flush()
        logger.info(f"Queued indexing job {job_id} source={canonical_uri}")
    except Exception as exc:
        logger.error(f"Kafka enqueue failed: {exc}")

    return {"document_id": job_id, "tenant_id": tenant_id, "filename": file.filename, "source_uri": canonical_uri, "status": "queued", "message": "File uploaded and queued for idempotent indexing"}
