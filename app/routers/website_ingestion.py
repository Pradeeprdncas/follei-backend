"""Fast, tenant-scoped website source API; crawling is worker-only."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AliasChoices, BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.schemas.api_envelope import api_envelope
from app.services.knowledge.categories import normalize_category
from app.services.knowledge.crawlers import supported_engines
from app.services.knowledge.website_ingestion import validate_public_url


router = APIRouter(prefix="/knowledge/websites", tags=["knowledge-websites"])
_settings = get_settings()


class WebsiteIngestRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=10, ge=1, le=25)
    category: str | None = None
    engine: str = Field(default="auto", pattern="^(auto|aiohttp|crawl4ai|scrapy)$")
    crawl_consent: bool = Field(
        validation_alias=AliasChoices("crawl_consent", "confirm_authorized"),
        description="Consent to crawl public pages. This is not proof of website ownership.",
    )


@router.get("/engines")
def engines():
    return api_envelope({"engines": supported_engines()})


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_website(
    payload: WebsiteIngestRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    if not payload.crawl_consent:
        raise HTTPException(status_code=422, detail="Crawl consent must be confirmed")
    try:
        validate_public_url(str(payload.url))
        category = normalize_category(payload.category) if payload.category else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant_uuid = UUID(tenant_id)
    from uuid import uuid4
    source = KnowledgeSource(
        id=uuid4(),
        tenant_id=tenant_uuid,
        name=f"Website: {payload.url.host}",
        source_type="website",
        status="queued",
        config={
            "url": str(payload.url), "max_pages": payload.max_pages,
            "engine": payload.engine, "category": category,
            "crawl_consent": True,
            "ownership_verification": "unverified",
        },
    )
    run = IngestionRun(id=uuid4(), tenant_id=tenant_uuid, source_id=source.id, status="queued")
    job = SourceIngestionJob(
        tenant_id=tenant_uuid,
        run_id=run.id,
        job_type="website_crawl",
        target=str(payload.url),
        status="queued",
        payload={"engine": payload.engine, "max_pages": payload.max_pages, "category": category},
    )
    db.add_all([source, run, job])
    db.commit()
    message = {
        "job_id": str(job.id), "run_id": str(run.id), "source_id": str(source.id),
        "tenant_id": tenant_id, "url": str(payload.url), "max_pages": payload.max_pages,
        "engine": payload.engine, "category": category,
    }
    try:
        ensure_topics()
        producer = get_producer()
        producer.send(_settings.KAFKA_TOPIC_WEBSITE_INGESTION, key=str(job.id), value=message)
        producer.flush()
    except Exception as exc:
        job.status = run.status = source.status = "failed"
        job.last_error = f"queue: {exc}"[:4000]
        run.error = "Website ingestion queue is unavailable"
        db.commit()
        raise HTTPException(status_code=503, detail="Website ingestion could not be queued") from exc

    return api_envelope(
        {
            "source": {
                "id": str(source.id), "type": "website", "status": source.status,
                "crawl_consent": True, "ownership_verification": "unverified",
            },
            "run": {"id": str(run.id), "status": run.status},
            "jobs": [{"id": str(job.id), "type": job.job_type, "status": job.status}],
            "status_url": f"/api/v1/onboarding/state",
        },
        accepted=True,
    )
