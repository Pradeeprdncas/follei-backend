"""Tenant-scoped safe website ingestion API."""
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id
from app.models.knowledge.indexing_job import IndexingJob
from app.routers.upload import UPLOAD_DIR, TARGET_CATEGORIES
from app.services.knowledge.website_ingestion import crawl_website
from app.services.knowledge.object_storage import store_source

router = APIRouter(prefix="/knowledge/websites", tags=["knowledge-websites"])
_settings = get_settings()


class WebsiteIngestRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=10, ge=1, le=25)
    category: str | None = None
    confirm_authorized: bool


@router.post("/ingest")
async def ingest_website(payload: WebsiteIngestRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    if not payload.confirm_authorized:
        raise HTTPException(status_code=422, detail="Website ownership or crawl authorization must be confirmed")
    category = payload.category.lower().strip() if payload.category else None
    if category and category not in TARGET_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown target category")
    try:
        pages = await crawl_website(str(payload.url), max_pages=payload.max_pages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not pages:
        raise HTTPException(status_code=422, detail="No crawlable text pages were found")
    job_id = uuid4()
    path = Path(UPLOAD_DIR) / f"{job_id}.txt"
    rendered = "\n\n".join(f"# {page['title']}\nSource URL: {page['url']}\n{page['text']}" for page in pages)
    path.write_text(rendered, encoding="utf-8")
    try:
        object_key = store_source(path, tenant_id=tenant_id, job_id=str(job_id))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Website was crawled but durable object storage is unavailable") from exc
    message = {"job_id": str(job_id), "tenant_id": tenant_id, "file_path": str(path), "filename": f"website-{payload.url.host}.txt", "source_uri": str(payload.url), "uploaded_by": "website_ingestion", "file_type": "txt", "category": category, "object_key": object_key}
    job = IndexingJob(id=job_id, tenant_id=UUID(tenant_id), status="queued", payload={**message, "crawl": {"page_count": len(pages)}})
    db.add(job); db.commit()
    try:
        ensure_topics(); producer = get_producer(); producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(job_id), value=message); producer.flush()
    except Exception as exc:
        job.status = "failed"; job.last_error = f"queue: {exc}"[:4000]; db.commit()
        raise HTTPException(status_code=503, detail="Website was crawled but indexing could not be queued") from exc
    return {"job_id": str(job_id), "status": "queued", "source_uri": str(payload.url), "pages_crawled": len(pages), "disposition": "pending"}
