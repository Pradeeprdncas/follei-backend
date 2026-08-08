"""Lead Import API router.

Primary: POST /leads/import  — sync csv.DictReader import (≤1000 rows, no job, no LLM)
Async:   POST /leads/import/async  — job-based import (>1000 rows, Celery)
Preview: POST /leads/import/preview — dry-run preview
"""

import csv
import io
import os
import re
import tempfile
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from loguru import logger

from app.database.session import get_db
from app.domains.lead_import.service import LeadImportService
from app.domains.lead_import.repository import LeadImportRepository
from app.domains.lead_import.schemas import (
    LeadImportUploadResponse,
    LeadImportJobResponse,
    LeadImportPreviewResponse,
    LeadImportCommitResponse,
    RowUpdateRequest,
    BulkActionRequest,
    BulkActionResponse,
)
from app.domains.lead_import.exceptions import JobNotFoundError, JobNotReadyError, LeadImportPolicyError
from app.domains.lead_import.constants import FileType
from app.domains.lead_import.utils import detect_file_type
from app.domains.lead_import.validators import (
    MINIMUM_ACCEPTED_LEADS,
    lead_import_policy,
    validate_lead_row,
    evaluate_lead_batch,
    is_blank_row,
)
from app.models.leads.lead import Lead
from app.domains.lead_import.models import LeadImportJob
from app.domains.lead_import.utils import split_full_name, normalize_email, normalize_phone, normalize_website
from app.models.knowledge.indexing_job import IndexingJob
from app.routers.upload import UPLOAD_DIR
from app.services.knowledge.object_storage import store_source
from app.services.knowledge.website_ingestion import crawl_website
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id, require_matching_tenant
from app.config.ferretdb import get_context_database

router = APIRouter(prefix="/leads/import", tags=["Lead Import"])
_settings = get_settings()
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MINIMUM_ONBOARDING_LEAD_ROWS = MINIMUM_ACCEPTED_LEADS


def _owned_job(db: Session, job_id: str, tenant_id: str) -> LeadImportJob:
    """Return an import job only when it belongs to the JWT tenant."""
    try:
        job = db.get(LeadImportJob, UUID(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Import job not found") from exc
    if not job or str(job.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=404, detail="Import job not found")
    return job

# ── Header normalisation map ─────────────────────────────────────
# Maps CSV column name variants → canonical field names
_HEADER_MAP: dict[str, str] = {}
for canonical, variants in [
    ("email",         ["email", "e-mail", "e mail", "mail", "email address", "email_address", "contact email", "contact_email", "email id", "email_id", "mail id", "mail_id"]),
    ("first_name",    ["first name", "firstname", "fname", "given name", "given_name", "forename", "first"]),
    ("last_name",     ["last name", "lastname", "lname", "surname", "family name", "family_name", "last"]),
    ("full_name",     ["name", "full name", "fullname", "contact name", "contact_name", "person name", "person_name"]),
    ("company",       ["company", "organization", "organisation", "org", "business", "firm", "account", "employer", "company name", "company_name", "business name", "business_name"]),
    ("phone",         ["phone", "mobile", "cell", "telephone", "tel", "contact", "contact no", "contact_no", "contact number", "contact_number", "phone number", "phone_number", "phone no", "phone_no", "mobile number", "mobile_number", "mobile no", "mobile_no", "phone #", "cell phone", "cellphone", "work phone", "home phone"]),
    ("whatsapp",      ["whatsapp", "whats app", "whats_app", "whatsapp number", "whatsapp_number", "whatsapp no", "whatsapp_no", "whatsapp phone", "whatsapp_phone"]),
    ("website",       ["website", "web", "url", "site", "domain", "web page", "web_page", "web site", "web_site"]),
    ("linkedin",      ["linkedin", "linked in", "linked_in", "linkedin url", "linkedin_url", "linkedin profile", "linkedin_profile", "linked in url", "linked in profile"]),
    ("designation",   ["designation", "title", "position", "role", "job title", "job_title", "job role", "job_role", "job position", "job_position"]),
    ("department",    ["department", "dept", "division", "unit", "team", "business unit", "business_unit"]),
    ("city",          ["city", "town", "locality", "location city", "location_city"]),
    ("state",         ["state", "province", "region", "territory"]),
    ("country",       ["country", "nation", "nationality"]),
    ("postal_code",   ["postal code", "postal_code", "zip", "zip code", "zip_code", "pincode", "pin code", "pin_code"]),
    ("industry",      ["industry", "sector", "vertical", "business type", "business_type", "category"]),
    ("notes",         ["notes", "comments", "remarks", "description", "additional info", "additional_info", "note"]),
]:
    for v in variants:
        _HEADER_MAP[v] = canonical
for c in ["email", "first_name", "last_name", "full_name", "company", "phone", "whatsapp", "website", "linkedin", "designation", "department", "city", "state", "country", "postal_code", "industry", "notes"]:
    _HEADER_MAP[c] = c


def _normalise_header(h: str) -> str:
    return h.lower().strip().replace("_", " ").replace("-", " ").strip()


def _parse_csv(content: str) -> list[dict]:
    """Parse CSV with csv.DictReader and normalise headers."""
    dialect = csv.Sniffer().sniff(content[:4096])
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    # Normalise headers
    reader.fieldnames = [_normalise_header(h) for h in reader.fieldnames]
    # Map to canonical field names
    mapped = []
    for row in reader:
        normalised = {}
        for raw_key, val in row.items():
            if raw_key in _HEADER_MAP:
                canonical = _HEADER_MAP[raw_key]
            else:
                canonical = raw_key
            stripped = val.strip() if val else ""
            if stripped:
                normalised[canonical] = stripped
        if normalised:
            mapped.append(normalised)
    return mapped


_RowImportResult = list[dict]  # list of {row_index, email, action, error?, lead_id?}


def _write_lead(db, tenant_id, row: dict) -> dict:
    """Insert or skip a single lead row. Returns result dict."""
    validation_errors = validate_lead_row(row)
    if validation_errors:
        return {"action": "skipped", "error": "; ".join(validation_errors)}
    email = row.get("email", "").strip().lower()

    # Dedup by email within tenant
    existing = None
    if email:
        existing = db.execute(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.email == email)
        ).scalar_one_or_none()
    if existing:
        return {"action": "duplicate", "error": f"Email already exists: {email}", "lead_id": str(existing.id)}

    first_name = row.get("first_name") or ""
    last_name = row.get("last_name") or ""

    # Handle full_name
    full_name = row.get("full_name")
    if full_name and not first_name:
        first_name, last_name = split_full_name(full_name)

    phone_raw = row.get("phone") or ""
    phone_int = 0
    if phone_raw:
        digits = "".join(c for c in str(phone_raw) if c.isdigit())[:15]
        phone_int = int(digits) if digits else 0

    lead = Lead(
        id=uuid4(),
        tenant_id=tenant_id,
        email=email,
        first_name=first_name.strip() or None,
        last_name=last_name.strip() or None,
        company=(row.get("company") or "").strip() or None,
        phone=phone_int,
        profile_data={key: value for key, value in row.items() if key not in {"email", "first_name", "last_name", "full_name", "company", "phone"}},
        status="new",
        verification_status="validated",
    )
    db.add(lead)
    db.flush()
    from app.services.knowledge.memory_store import upsert_lead_import_memory
    upsert_lead_import_memory(
        tenant_id=str(tenant_id), lead_id=str(lead.id), import_job_id=None,
        record={"raw_data": row, "normalized_data": row, "extracted_data": row},
    )
    return {"action": "created", "lead_id": str(lead.id)}


# ── Response schemas ─────────────────────────────────────────────

class ImportResult(BaseModel):
    created: int
    duplicates: int
    skipped: int
    total: int
    errors: list[dict]
    accepted_rows: int
    rejected_rows: int
    can_proceed: bool
    policy: dict
    flow_enrollment: dict | None = None


class PreviewRow(BaseModel):
    row_index: int
    data: dict
    errors: list[str]

class PreviewResult(BaseModel):
    rows: list[PreviewRow]
    total: int
    valid_rows: int
    invalid_rows: int
    batch_errors: list[dict]
    policy: dict


# ── POST /leads/import — sync direct import ──────────────────────

@router.post("", response_model=ImportResult, status_code=201)
async def import_leads(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    run_ai: bool = Form(False),
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Import leads from CSV directly — no job, no LLM.

    Uses csv.DictReader to parse, normalises headers, deduplicates by email.
    Limits: ≤1000 rows. For larger files use POST /leads/import/async.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    rows = _parse_csv(text)
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    batch = evaluate_lead_batch(rows)
    accepted_rows = batch["accepted_rows"]
    rejected_preview = [
        {"row_index": item["row_index"], "reasons": item["reasons"]}
        for item in batch["rejected"]
    ]
    if accepted_rows < MINIMUM_ONBOARDING_LEAD_ROWS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "minimum_accepted_rows_not_met",
                "minimum_accepted_rows": MINIMUM_ONBOARDING_LEAD_ROWS,
                "accepted_rows": accepted_rows,
                "rejected_rows": len(rows) - accepted_rows,
                "row_errors": rejected_preview[:100],
                "partial_accept": True,
            },
        )

    if len(rows) > 1000:
        raise HTTPException(
            status_code=413,
            detail=f"CSV has {len(rows)} rows (max 1000 for sync import). Use POST /leads/import/async for large files."
        )

    require_matching_tenant(tenant_id, authenticated_tenant_id)
    try:
        tenant_uuid = UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id")

    results: list[dict] = []
    try:
        # Partial accept is literal: rejected rows are logged in the response
        # and never passed to the persistence function. The batch proceeds only
        # because at least 50 valid rows remain after these rejections.
        for item in batch["accepted"]:
            i, row = item["row_index"], item["row"]
            result = _write_lead(db, tenant_uuid, row)
            result["row_index"] = i
            results.append(result)

        db.commit()

        created = sum(1 for r in results if r["action"] == "created")
        duplicates = sum(1 for r in results if r["action"] == "duplicate")
        skipped = sum(1 for r in results if r["action"] == "skipped") + batch["rejected_rows"]
        errors = [
            {"row_index": item["row_index"], "error": "; ".join(item["reasons"]), "reasons": item["reasons"]}
            for item in batch["rejected"]
        ] + [{"row_index": r["row_index"], "error": r.get("error", ""), "lead_id": r.get("lead_id")} for r in results if r["action"] != "created"]

        # Optional AI enrichment after insert (async)
        if run_ai and created > 0:
            import asyncio
            try:
                from app.domains.lead_import.scoring import calculate_quality_score
                for r in results:
                    if r["action"] == "created" and r.get("lead_id"):
                        lead = db.get(Lead, UUID(r["lead_id"]))
                        if lead:
                            lead_data = {
                                "first_name": lead.first_name,
                                "last_name": lead.last_name,
                                "company": lead.company,
                                "email": lead.email,
                                "phone": str(lead.phone) if lead.phone else "",
                            }
                            quality = calculate_quality_score(lead_data)
                            logger.info("AI enrichment done for lead %s: score=%s", lead.id, quality.get("score"))
            except Exception as e:
                logger.warning("AI enrichment failed (non-fatal): %s", e)

        from app.services.flows.service import enroll_leads
        created_ids = [item["lead_id"] for item in results if item.get("action") == "created"]
        flow_enrollment = enroll_leads(db, tenant_uuid, created_ids, "lead_import") if created_ids else {"status": "not_enrolled", "enrolled": 0, "reason": "no_new_leads"}
        return ImportResult(
            created=created, duplicates=duplicates, skipped=skipped, total=len(rows), errors=errors,
            accepted_rows=accepted_rows, rejected_rows=len(rows) - accepted_rows,
            can_proceed=accepted_rows >= MINIMUM_ONBOARDING_LEAD_ROWS,
            policy=lead_import_policy(), flow_enrollment=flow_enrollment,
        )
    except Exception:
        db.rollback()
        raise


# ── POST /leads/import/preview — dry run ─────────────────────────

@router.post("/preview", response_model=PreviewResult)
async def preview_import(
    file: UploadFile = File(...),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Preview CSV import — parse and show rows with validation errors, no DB writes."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    rows = _parse_csv(text)
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    preview_rows = []
    for i, row in enumerate(rows):
        errs = validate_lead_row(row)
        if not row.get("email") and not row.get("first_name") and not row.get("full_name"):
            errs = ["Blank row"] + errs
        preview_rows.append(PreviewRow(row_index=i, data=row, errors=errs))

    valid = sum(not row.errors for row in preview_rows)
    batch_errors = []
    if valid < MINIMUM_ONBOARDING_LEAD_ROWS:
        batch_errors.append({"code": "minimum_accepted_rows_not_met", "minimum_accepted_rows": MINIMUM_ONBOARDING_LEAD_ROWS, "accepted_rows": valid, "rejected_rows": len(preview_rows) - valid})
    return PreviewResult(
        rows=preview_rows,
        total=len(preview_rows),
        valid_rows=valid,
        invalid_rows=len(preview_rows) - valid,
        batch_errors=batch_errors,
        policy={**lead_import_policy(), "can_proceed": valid >= MINIMUM_ONBOARDING_LEAD_ROWS},
    )


# ── POST /leads/import/async — job-based for large files ─────────

def get_service(db: Session = Depends(get_db)) -> LeadImportService:
    repo = LeadImportRepository(db)
    return LeadImportService(repo)


@router.post("/async", response_model=LeadImportUploadResponse, status_code=201)
async def import_leads_async(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Upload a large CSV for async processing (>1000 rows). Creates a background job."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    require_matching_tenant(tenant_id, authenticated_tenant_id)
    try:
        file_type = detect_file_type(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    content = await file.read()
    if file_type == FileType.CSV:
        try:
            candidate_rows = _parse_csv(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, csv.Error):
            candidate_rows = _parse_csv(content.decode("latin-1"))
        if len(candidate_rows) < MINIMUM_ONBOARDING_LEAD_ROWS:
            raise HTTPException(status_code=422, detail={"code": "minimum_accepted_rows_not_met", "minimum_accepted_rows": MINIMUM_ONBOARDING_LEAD_ROWS, "accepted_rows": 0, "candidate_rows": len(candidate_rows), "partial_accept": True})
    fd, temp_path = tempfile.mkstemp(suffix=f".{file_type}")
    try:
        os.write(fd, content)
        os.close(fd)

        job = await service.process_upload(
            tenant_id=UUID(tenant_id),
            filename=file.filename,
            file_type=file_type,
            file_path=temp_path,
            uploaded_by=None,
        )

        return LeadImportUploadResponse(
            job_id=str(job.id),
            public_id=job.public_id or "",
            filename=job.filename,
            file_type=job.file_type,
            status=job.status,
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


@router.post("/upload", response_model=LeadImportUploadResponse, status_code=201)
async def import_leads_from_file(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Import leads from CSV, Excel, PDF, DOCX, text, or supported images.

    The returned job exposes review/commit endpoints.  Commit writes the
    normalized operational record to PostgreSQL and the complete extracted
    source record to tenant-scoped FerretDB memory.
    """
    return await import_leads_async(
        tenant_id=tenant_id,
        file=file,
        service=service,
        authenticated_tenant_id=authenticated_tenant_id,
    )


@router.post("/{job_id}/crawl-links")
async def crawl_imported_lead_links(
    job_id: str,
    confirm_authorized: bool = False,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Crawl URLs found in committed lead records and queue their knowledge ingestion.

    Each lead URL produces a normal indexing job, so parsed text is persisted
    through the established PostgreSQL, Qdrant, and FerretDB pipeline instead
    of creating a lead-import-only data silo.
    """
    if not confirm_authorized:
        raise HTTPException(status_code=422, detail="Website ownership or crawl authorization must be confirmed")
    job = _owned_job(db, job_id, authenticated_tenant_id)
    rows = LeadImportRepository(db).get_rows_by_job(job.id, status="committed")
    url_provenance: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        for value in (row.raw_data or {}, row.normalized_data or {}, row.extracted_data or {}):
            for match in _URL_PATTERN.findall(str(value)):
                url = match.rstrip(".,;)")
                provenance = url_provenance.setdefault(url, {"lead_ids": set(), "lead_import_row_ids": set()})
                if row.lead_id:
                    provenance["lead_ids"].add(str(row.lead_id))
                provenance["lead_import_row_ids"].add(str(row.id))
    queued: list[dict] = []
    failures: list[dict] = []
    for url, provenance in sorted(url_provenance.items()):
        try:
            source_metadata = {
                "lead_ids": sorted(provenance["lead_ids"]),
                "lead_import_row_ids": sorted(provenance["lead_import_row_ids"]),
                "lead_import_job_ids": [str(job.id)],
                "ingestion_origin": "lead_import_link_crawl",
            }
            sources = await crawl_website(url, max_pages=10, include_assets=True)
            pages = [source for source in sources if "content" not in source]
            if not pages:
                continue
            index_job_id = uuid4()
            path = os.path.join(str(UPLOAD_DIR), f"lead-url-{index_job_id}.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n\n".join(f"# {page['title']}\nSource URL: {page['url']}\n{page['text']}" for page in pages))
            object_key = store_source(path, tenant_id=str(job.tenant_id), job_id=str(index_job_id))
            payload = {"job_id": str(index_job_id), "tenant_id": str(job.tenant_id), "file_path": path, "filename": f"lead-url-{index_job_id}.txt", "source_uri": url, "uploaded_by": "lead_import_link_crawl", "file_type": "txt", "category": None, "object_key": object_key, "lead_import_job_id": str(job.id), "lead_ids": source_metadata["lead_ids"], "source_metadata": source_metadata}
            db.add(IndexingJob(id=index_job_id, tenant_id=job.tenant_id, status="queued", payload=payload))
            ensure_topics(); producer = get_producer(); producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(index_job_id), value=payload); producer.flush()
            for asset in (source for source in sources if "content" in source):
                asset_job_id = uuid4()
                asset_path = os.path.join(str(UPLOAD_DIR), f"lead-url-{asset_job_id}.{asset['file_type']}")
                with open(asset_path, "wb") as handle:
                    handle.write(asset["content"])
                asset_key = store_source(asset_path, tenant_id=str(job.tenant_id), job_id=str(asset_job_id))
                asset_payload = {"job_id": str(asset_job_id), "tenant_id": str(job.tenant_id), "file_path": asset_path, "filename": asset["filename"], "source_uri": asset["url"], "uploaded_by": "lead_import_link_crawl", "file_type": asset["file_type"], "category": None, "object_key": asset_key, "lead_import_job_id": str(job.id), "lead_ids": source_metadata["lead_ids"], "source_metadata": source_metadata}
                db.add(IndexingJob(id=asset_job_id, tenant_id=job.tenant_id, status="queued", payload=asset_payload))
                producer.send(_settings.KAFKA_TOPIC_INDEXING, key=str(asset_job_id), value=asset_payload)
            producer.flush()
            queued.append({"url": url, "job_id": str(index_job_id), "lead_ids": source_metadata["lead_ids"], "pages": len(pages), "assets_discovered": len(sources) - len(pages)})
        except Exception as exc:
            failures.append({"url": url, "error": str(exc)[:300]})
    queued_lead_ids = sorted({
        str(lead_id)
        for provenance in url_provenance.values()
        for lead_id in provenance["lead_ids"]
    })
    queued_urls = sorted({str(item["url"]) for item in queued})
    pre_nurturing = {
        "system": "System 1",
        "stage": "processing" if queued else ("needs_attention" if failures else "no_urls_found"),
        "import_job_id": str(job.id),
        "urls_queued": queued_urls,
        "crawl_jobs": [str(item["job_id"]) for item in queued],
        "failures": failures,
    }
    if queued_lead_ids:
        for lead in db.query(Lead).filter(
            Lead.tenant_id == job.tenant_id,
            Lead.id.in_([UUID(value) for value in queued_lead_ids]),
        ).all():
            lead.profile_data = {
                **(lead.profile_data or {}),
                "pre_nurturing": pre_nurturing,
            }
        try:
            memory = get_context_database()
            for lead_id in queued_lead_ids:
                memory["lead_import_memory"].update_one(
                    {"tenant_id": str(job.tenant_id), "lead_id": lead_id},
                    {"$set": {"pre_nurturing": pre_nurturing}},
                    upsert=True,
                )
                memory["tenant_context"].update_one(
                    {
                        "tenant_id": str(job.tenant_id),
                        "subject_type": "lead",
                        "subject_id": lead_id,
                    },
                    {"$set": {"pre_nurturing": pre_nurturing}},
                    upsert=True,
                )
        except Exception as exc:
            logger.warning("System 1 FerretDB status mirror skipped: {}", exc)
    db.commit()
    return {"import_job_id": str(job.id), "urls_found": len(url_provenance), "queued": queued, "failures": failures}


# ── Existing job routes (kept for backward compat) ───────────────

@router.get("/{job_id}/storage-verification")
def verify_lead_import_storage(
    job_id: str,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Verify canonical leads, full import memory, and crawled memory for one job."""
    job = _owned_job(db, job_id, authenticated_tenant_id)
    rows = LeadImportRepository(db).get_rows_by_job(job.id)
    committed_rows = [row for row in rows if row.status == "committed" and row.lead_id]
    lead_ids = sorted({str(row.lead_id) for row in committed_rows})
    crawl_jobs = [
        item
        for item in db.query(IndexingJob).filter(IndexingJob.tenant_id == job.tenant_id).all()
        if str((item.payload or {}).get("lead_import_job_id") or "") == str(job.id)
    ]
    document_ids = sorted({str(item.document_id) for item in crawl_jobs if item.document_id})
    ferret_error = None
    raw_memory_count = 0
    crawled_memory_count = 0
    crawled_view_count = 0
    try:
        context = get_context_database()
        if lead_ids:
            raw_memory_count = context["lead_import_memory"].count_documents(
                {"tenant_id": str(job.tenant_id), "lead_id": {"$in": lead_ids}}
            )
        crawled_memory_count = context["knowledge_document_memory"].count_documents(
            {"tenant_id": str(job.tenant_id), "lead_import_job_ids": str(job.id)}
        )
        crawled_view_count = context["knowledge_document_views"].count_documents(
            {"tenant_id": str(job.tenant_id), "lead_import_job_ids": str(job.id)}
        )
    except Exception as exc:
        ferret_error = f"{type(exc).__name__}: {exc}"
    return {
        "job_id": str(job.id),
        "status": job.status,
        "postgres": {
            "source_rows": len(rows),
            "committed_rows": len(committed_rows),
            "linked_lead_ids": lead_ids,
            "crawl_jobs": len(crawl_jobs),
            "indexed_crawl_documents": len(document_ids),
            "crawl_document_ids": document_ids,
        },
        "ferretdb": {
            "raw_lead_memories": raw_memory_count,
            "crawled_document_memories": crawled_memory_count,
            "crawled_document_views": crawled_view_count,
            "error": ferret_error,
        },
        "consistent": ferret_error is None and raw_memory_count == len(lead_ids),
        "crawl_projection_complete": bool(crawl_jobs) and len(document_ids) == crawled_memory_count == crawled_view_count,
    }


@router.get("/{job_id}", response_model=LeadImportJobResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Get the status and progress of a lead import job."""
    repo = LeadImportRepository(db)
    job = _owned_job(db, job_id, authenticated_tenant_id)

    return LeadImportJobResponse(
        id=str(job.id),
        public_id=job.public_id or "",
        tenant_id=str(job.tenant_id),
        filename=job.filename,
        file_type=job.file_type,
        status=job.status,
        uploaded_by=job.uploaded_by,
        total_rows=job.total_rows,
        valid_rows=job.valid_rows,
        duplicate_rows=job.duplicate_rows,
        invalid_rows=job.invalid_rows,
        statistics=job.statistics,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/preview", response_model=LeadImportPreviewResponse)
def get_preview(
    job_id: str,
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Preview extracted leads before committing."""
    _owned_job(service.repo.db, job_id, authenticated_tenant_id)
    try:
        preview = service.get_preview(UUID(job_id))
        return LeadImportPreviewResponse(**preview)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobNotReadyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LeadImportPolicyError as e:
        raise HTTPException(status_code=422, detail=e.details)


@router.post("/{job_id}/commit", response_model=LeadImportCommitResponse)
def commit_import(
    job_id: str,
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Commit selected rows from the import into the Lead table."""
    _owned_job(service.repo.db, job_id, authenticated_tenant_id)
    try:
        result = service.commit(UUID(job_id))
        from app.domains.lead_import.models import LeadImportRow
        from app.services.flows.service import enroll_leads
        lead_ids = [row[0] for row in service.repo.db.query(LeadImportRow.lead_id).filter(LeadImportRow.job_id == UUID(job_id), LeadImportRow.lead_id.isnot(None)).all()]
        result["flow_enrollment"] = enroll_leads(service.repo.db, authenticated_tenant_id, lead_ids, "lead_import_job") if lead_ids else {"status": "not_enrolled", "enrolled": 0, "reason": "no_new_leads"}
        return LeadImportCommitResponse(**result)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobNotReadyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LeadImportPolicyError as e:
        raise HTTPException(status_code=422, detail=e.details)


@router.put("/{job_id}/rows/{row_id}")
def update_row(
    job_id: str,
    row_id: str,
    body: RowUpdateRequest,
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Edit a single row's extracted data before committing."""
    _owned_job(service.repo.db, job_id, authenticated_tenant_id)
    try:
        result = service.update_row_data(UUID(row_id), body.updates)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Row not found: {row_id}")
        return result
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{job_id}/rows/{row_id}/ignore")
def ignore_row(
    job_id: str,
    row_id: str,
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Mark a single row as ignored/skipped."""
    _owned_job(service.repo.db, job_id, authenticated_tenant_id)
    try:
        result = service.ignore_row(UUID(row_id))
        if result is None:
            raise HTTPException(status_code=404, detail=f"Row not found: {row_id}")
        return result
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{job_id}/bulk", response_model=BulkActionResponse)
def bulk_action(
    job_id: str,
    body: BulkActionRequest,
    service: LeadImportService = Depends(get_service),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Perform a bulk action (ignore/reset/spam/select/deselect) on multiple rows."""
    _owned_job(service.repo.db, job_id, authenticated_tenant_id)
    try:
        result = service.bulk_action(UUID(job_id), body.action, body.row_ids)
        return BulkActionResponse(**result)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
