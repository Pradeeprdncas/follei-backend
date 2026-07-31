"""Queue safe inbound email attachments through Follei System 1."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.models.knowledge.indexing_job import IndexingJob
from app.services.knowledge.object_storage import store_source

_settings = get_settings()
_UPLOAD_DIR = Path("uploads") / "email"
_ALLOWED = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".ppt", ".pptx", ".eml", ".msg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class EmailAttachmentRejected(ValueError):
    pass


def _safe_filename(value: str) -> str:
    name = Path(value or "attachment").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return cleaned[:180] or "attachment"


def queue_email_attachment(
    db: Session,
    *,
    tenant_id: str,
    lead_id: str,
    provider_message_id: str,
    filename: str,
    content_type: str | None,
    content_bytes: bytes,
) -> dict:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in _ALLOWED:
        raise EmailAttachmentRejected(f"Unsupported attachment type: {extension or '(none)'}")
    if not content_bytes:
        raise EmailAttachmentRejected("Empty attachment")
    if len(content_bytes) > _settings.EMAIL_ATTACHMENT_MAX_BYTES:
        raise EmailAttachmentRejected("Attachment exceeds configured size limit")

    job_id = uuid4()
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _UPLOAD_DIR / f"{job_id}{extension}"
    local_path.write_bytes(content_bytes)
    object_key = store_source(local_path, tenant_id=tenant_id, job_id=str(job_id))
    message_fingerprint = hashlib.sha256(provider_message_id.encode("utf-8", errors="ignore")).hexdigest()[:24]
    source_uri = f"email://gmail/{tenant_id}/{message_fingerprint}/{safe_name}"
    source_metadata = {
        "source": "inbound_email_attachment",
        "lead_ids": [str(lead_id)],
        "provider_message_id_hash": message_fingerprint,
        "content_type": content_type,
        "original_filename": safe_name,
    }
    payload = {
        "job_id": str(job_id),
        "tenant_id": str(tenant_id),
        "file_path": str(local_path),
        "filename": safe_name,
        "source_uri": source_uri,
        "uploaded_by": "gmail_inbound_worker",
        "file_type": extension.lstrip("."),
        "category": None,
        "object_key": object_key,
        "lead_ids": [str(lead_id)],
        "source_metadata": source_metadata,
    }
    job = IndexingJob(
        id=job_id,
        tenant_id=UUID(str(tenant_id)),
        status="queued",
        payload=payload,
    )
    db.add(job)
    db.commit()
    try:
        ensure_topics()
        producer = get_producer()
        producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(job_id), value=payload)
        producer.flush()
    except Exception as exc:
        job.status = "failed"
        job.last_error = f"queue: {exc}"[:4000]
        db.commit()
        raise
    return {
        "job_id": str(job_id),
        "filename": safe_name,
        "content_type": content_type,
        "size_bytes": len(content_bytes),
        "object_key": object_key,
        "source_uri": source_uri,
        "status": "queued",
    }
