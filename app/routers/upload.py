"""Upload endpoint — accepts file, saves to disk, sends to Kafka for indexing."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pathlib import Path
import shutil
import uuid
from app.config.settings import get_settings
from app.config.kafka import get_producer, ensure_topics
from loguru import logger

router = APIRouter(prefix="/upload", tags=["upload"])
_settings = get_settings()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
):
    """
    Upload a document file.
    Saves to disk and queues for indexing via Kafka.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save file
    doc_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    save_path = UPLOAD_DIR / f"{doc_id}{ext}"

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"File save failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Send to Kafka for async indexing
    try:
        ensure_topics()
        producer = get_producer()
        message = {
            "document_id": doc_id,
            "tenant_id": tenant_id,
            "file_path": str(save_path),
            "filename": file.filename,
            "file_type": ext.lstrip(".").lower(),
        }
        producer.send(_settings.KAFKA_TOPIC_INDEXING, key=doc_id, value=message)
        producer.flush()
        logger.info(f"Queued document {doc_id} for indexing")
    except Exception as e:
        logger.error(f"Kafka enqueue failed: {e}")
        # Don't fail the upload if Kafka is down — we can re-index manually

    return {
        "document_id": doc_id,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "status": "queued",
        "message": "File uploaded and queued for indexing",
    }
