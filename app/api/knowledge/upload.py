import uuid
import shutil
import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from loguru import logger

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def _run_indexing(file_path: str, tenant_id: str) -> None:
    try:
        from app.services.rag.pipelines.indexing import index_document
        doc_id = await index_document(file_path=file_path, tenant_id=tenant_id)
        logger.info(f"Indexing complete for tenant={tenant_id}, doc_id={doc_id}")
    except Exception as exc:
        logger.error(f"Background indexing failed for {file_path}: {exc}")


@router.post("/", summary="Upload and index a document")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    doc_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    save_path = UPLOAD_DIR / f"{doc_id}{ext}"

    try:
        with save_path.open("wb") as buf:
            shutil.copyfileobj(file.file, buf)
        logger.info(f"Saved upload: {save_path} (tenant={tenant_id})")
    except Exception as exc:
        logger.error(f"File save failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    def _compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()

    try:
        content_hash = _compute_file_hash(str(save_path))
        from app.database.session import get_db
        from app.models.knowledge.document import Document
        from sqlalchemy.exc import IntegrityError

        db = next(get_db())
        try:
            existing = db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.content_hash == content_hash
            ).first()

            if existing:
                logger.info(f"Duplicate upload detected: {existing.id} (hash: {content_hash[:16]}...)")
                save_path.unlink(missing_ok=True)
                db.close()
                return {
                    "document_id": str(existing.id),
                    "tenant_id": tenant_id,
                    "filename": file.filename,
                    "status": existing.status,
                    "message": "Document already exists with same content",
                    "skipped": True,
                }
        finally:
            db.close()
    except IntegrityError:
        from app.database.session import get_db
        from app.models.knowledge.document import Document
        db = next(get_db())
        try:
            existing = db.query(Document).filter(
                Document.tenant_id == tenant_id,
                Document.content_hash == content_hash
            ).first()
            if existing:
                save_path.unlink(missing_ok=True)
                return {
                    "document_id": str(existing.id),
                    "tenant_id": tenant_id,
                    "filename": file.filename,
                    "status": existing.status,
                    "message": "Document already exists (race condition handled)",
                    "skipped": True,
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Idempotency check failed: {e}")

    background_tasks.add_task(_run_indexing, str(save_path), tenant_id)

    return {
        "document_id": doc_id,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "status": "indexing",
        "message": "File uploaded — indexing running in background. Query /chat once done.",
    }
