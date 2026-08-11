"""Build the complete UI state from PostgreSQL control-plane records only."""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.knowledge.document import Document, KnowledgeSource
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.ingestion import CategorySummary, IngestionRun, OnboardingConfirmation
from app.models.knowledge.ingestion import SourceIngestionJob
from app.models.knowledge.indexing_job import IndexingJob
from app.models.onboarding_profile import OnboardingProfile
from app.services.knowledge.categories import CATEGORY_DEFINITIONS, MANDATORY_GROUPS, canonical_taxonomy_key


VALID_RESOLUTIONS = {"provided", "not_applicable", "confidential", "continue_without"}
TERMINAL_RUN_STATUSES = {"completed", "partial", "failed"}
TERMINAL_INDEXING_STATUSES = {"indexed", "completed", "ready", "failed", "dead_lettered", "dead_letter", "error"}


def _safe_job_progress(job: SourceIngestionJob) -> dict[str, object]:
    """Expose useful counters while keeping arbitrary/internal job payload out."""
    payload = dict(job.payload or {})
    allowed = (
        "resource", "stage", "selected_engine", "record_count",
        "pages_discovered", "documents_discovered", "items_queued",
        "current_url",
    )
    return {key: payload[key] for key in allowed if payload.get(key) is not None}


def _fact_label(payload: dict | None) -> str:
    value = payload or {}
    for key in ("name", "title", "question", "label", "subject", "description", "value"):
        if value.get(key):
            return str(value[key]).strip()[:180]
    return str(value).strip()[:180]


def _run_stage(run: IngestionRun, source_jobs: list[SourceIngestionJob], indexing_jobs: list[IndexingJob]) -> str:
    if run.status in TERMINAL_RUN_STATUSES:
        return run.status
    if any(job.status in {"running", "retrying"} and job.job_type == "website_crawl" for job in source_jobs):
        return "crawling_website"
    if any(job.status in {"running", "retrying"} and job.job_type.startswith("google_") for job in source_jobs):
        return "syncing_google_workspace"
    if indexing_jobs:
        return "indexing"
    return "queued"


def _run_progress_percent(run: IngestionRun, source_jobs: list[SourceIngestionJob], indexing_jobs: list[IndexingJob]) -> int:
    if run.status == "completed":
        return 100
    source_done = sum(job.status in {"completed", "failed"} for job in source_jobs)
    source_fraction = source_done / len(source_jobs) if source_jobs else 0.0
    if not indexing_jobs:
        return round(source_fraction * 40)
    indexing_done = sum(str(job.status or "").lower() in TERMINAL_INDEXING_STATUSES for job in indexing_jobs)
    return min(99, round(40 + 60 * indexing_done / len(indexing_jobs)))


def build_ingestion_run_state(db: Session, tenant_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, object] | None:
    """Build one source run's live, frontend-safe PostgreSQL projection."""
    run = db.query(IngestionRun).filter(
        IngestionRun.id == run_id,
        IngestionRun.tenant_id == tenant_id,
    ).first()
    if run is None:
        return None
    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.id == run.source_id,
        KnowledgeSource.tenant_id == tenant_id,
    ).first()
    source_jobs = db.query(SourceIngestionJob).filter(
        SourceIngestionJob.run_id == run.id,
        SourceIngestionJob.tenant_id == tenant_id,
    ).order_by(SourceIngestionJob.created_at, SourceIngestionJob.id).all()
    indexing_jobs = db.query(IndexingJob).filter(
        IndexingJob.tenant_id == tenant_id,
        IndexingJob.payload["source_metadata"]["ingestion_run_id"].as_string() == str(run.id),
    ).all()
    document_ids = {job.document_id for job in indexing_jobs if job.document_id}
    documents = (
        db.query(Document).filter(Document.tenant_id == tenant_id, Document.id.in_(document_ids)).all()
        if document_ids else []
    )
    facts = (
        db.query(BusinessFactDraft).filter(
            BusinessFactDraft.tenant_id == tenant_id,
            BusinessFactDraft.document_id.in_(document_ids),
        ).all()
        if document_ids else []
    )
    categories: dict[str, dict[str, object]] = {}
    for document in documents:
        raw = document.primary_category or document.category
        if not raw:
            continue
        try:
            key = canonical_taxonomy_key(raw)
        except ValueError:
            continue
        row = categories.setdefault(key, {"key": key, "item_count": 0, "document_count": 0, "sample_items": []})
        row["document_count"] = int(row["document_count"]) + 1
    for fact in facts:
        try:
            key = canonical_taxonomy_key(fact.fact_type)
        except ValueError:
            continue
        row = categories.setdefault(key, {"key": key, "item_count": 0, "document_count": 0, "sample_items": []})
        row["item_count"] = int(row["item_count"]) + 1
        label = _fact_label(fact.payload)
        samples = row["sample_items"]
        if label and isinstance(samples, list) and label not in samples and len(samples) < 3:
            samples.append(label)
    supported_category_keys = {definition.key for definition in CATEGORY_DEFINITIONS}
    for row in categories.values():
        row["status"] = "found" if int(row["item_count"]) else "partial"
        row["items_endpoint"] = (
            f"/api/v1/onboarding/categories/{row['key']}/items?source_id={run.source_id}"
            if row["key"] in supported_category_keys else None
        )

    jobs = [{
        "id": str(job.id),
        "type": job.job_type,
        "status": job.status,
        "attempt": int(job.attempt or 0),
        "error": _client_job_error(job.job_type, job.last_error),
        "progress": _safe_job_progress(job),
    } for job in source_jobs]
    jobs.extend({
        "id": str(job.id),
        "type": "document_indexing",
        "status": job.status,
        "attempt": int(job.attempt_count or 0),
        "error": "Document indexing failed" if job.last_error else None,
        "document_id": str(job.document_id) if job.document_id else None,
    } for job in indexing_jobs)
    stage = _run_stage(run, source_jobs, indexing_jobs)
    source_progress = [dict(job.payload or {}) for job in source_jobs]
    discovered_documents = max(
        (int(payload.get("documents_discovered") or 0) for payload in source_progress),
        default=int(run.document_count or 0),
    )
    return {
        "run_id": str(run.id),
        "source": {
            "id": str(source.id) if source else str(run.source_id),
            "name": source.name if source else None,
            "type": source.source_type if source else None,
            "status": source.status if source else None,
        },
        "status": run.status,
        "stage": stage,
        "terminal": run.status in TERMINAL_RUN_STATUSES,
        "progress_percent": _run_progress_percent(run, source_jobs, indexing_jobs),
        "counts": {
            "pages_discovered": int(run.page_count or 0),
            "documents_discovered": discovered_documents,
            "records_discovered": sum(int(payload.get("record_count") or 0) for payload in source_progress),
            "items_queued": sum(int(payload.get("items_queued") or 0) for payload in source_progress),
            "documents_indexed": sum(str(job.status or "").lower() in {"indexed", "completed", "ready"} for job in indexing_jobs),
            "categories_found": len(categories),
            "items_extracted": len(facts),
        },
        "jobs": jobs,
        "results": {
            "documents": [{
                "id": str(document.id),
                "title": document.title,
                "source_uri": document.source_uri,
                "status": document.status,
                "category": document.primary_category or document.category,
                "summary": document.summary,
                "chunk_count": int(document.total_chunks or 0),
            } for document in documents],
            "categories": sorted(categories.values(), key=lambda row: str(row["key"])),
        },
        "error": "Knowledge ingestion failed" if run.error else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _client_job_error(job_type: str, error: str | None) -> str | None:
    """Map internal worker diagnostics to stable frontend-safe messages."""
    if not error:
        return None
    if job_type.startswith("google_"):
        return "Google Workspace sync failed"
    if job_type == "hubspot_sync":
        return "HubSpot sync failed"
    if job_type == "website_crawl":
        return "Website ingestion failed"
    return "Knowledge ingestion failed"


def _category_rows(db: Session, tenant_id: uuid.UUID) -> list[dict[str, object]]:
    stored = {
        row.category_key: row
        for row in db.query(CategorySummary).filter(CategorySummary.tenant_id == tenant_id).all()
    }
    rows: list[dict[str, object]] = []
    for definition in CATEGORY_DEFINITIONS:
        stored_row = stored.get(definition.key)
        mode = stored_row.display_mode if stored_row else "enumerable"
        count = stored_row.item_count if stored_row else 0
        display: dict[str, object] = {"mode": mode}
        if mode == "aggregate":
            display.update({
                "breakdown": list(stored_row.breakdown or []) if stored_row else [],
                "sample_items": list(stored_row.sample_items or []) if stored_row else [],
            })
        else:
            reviewed = min(stored_row.reviewed_count or 0, count) if stored_row else 0
            display.update({
                "items_endpoint": f"/api/v1/onboarding/categories/{definition.key}/items",
                "review_progress": {"reviewed": reviewed, "total": count},
            })
        rows.append({
            "key": definition.key,
            "label": definition.label,
            "category_group": definition.group,
            "mandatory_group": definition.mandatory_group,
            "status": stored_row.status if stored_row else "missing",
            "count": count,
            "summary": stored_row.summary if stored_row else None,
            "confidence": float(stored_row.confidence) if stored_row and stored_row.confidence is not None else None,
            "needs_review": stored_row.needs_review if stored_row else False,
            "display": display,
        })
    return rows


def evaluate_readiness(
    categories: list[dict[str, object]],
    confirmation_map: dict[str, object],
    profile_missing: list[str],
) -> dict[str, object]:
    """Evaluate mandatory groups; one populated member satisfies each group."""
    found_by_mandatory_group: dict[str, list[str]] = defaultdict(list)
    for category in categories:
        mandatory_group = category.get("mandatory_group")
        if mandatory_group and category.get("status") in {"found", "partial"} and int(category.get("count") or 0) > 0:
            found_by_mandatory_group[str(mandatory_group)].append(str(category["key"]))

    missing_groups = [key for key in MANDATORY_GROUPS if not found_by_mandatory_group[key]]
    confirmations_needed = [key for key in missing_groups if key not in confirmation_map]
    unsafe_confirmations = {
        key for key, row in confirmation_map.items()
        if getattr(row, "resolution", None) == "continue_without"
    }
    can_continue = not profile_missing and not confirmations_needed
    return {
        "found_by_mandatory_group": dict(found_by_mandatory_group),
        "missing_groups": missing_groups,
        "confirmations_needed": confirmations_needed,
        "can_continue": can_continue,
        "ready_for_autonomous_actions": can_continue and not missing_groups and not unsafe_confirmations,
    }


def build_onboarding_state(db: Session, tenant_id: uuid.UUID) -> dict[str, object]:
    profile = db.query(OnboardingProfile).filter(OnboardingProfile.tenant_id == tenant_id).first()
    sources = db.query(KnowledgeSource).filter(KnowledgeSource.tenant_id == tenant_id).order_by(KnowledgeSource.created_at).all()
    runs = db.query(IngestionRun).filter(IngestionRun.tenant_id == tenant_id).order_by(IngestionRun.created_at.desc()).all()
    source_jobs_by_run: dict[str, list[dict[str, object]]] = defaultdict(list)
    source_job_models_by_run: dict[str, list[SourceIngestionJob]] = defaultdict(list)
    for job in db.query(SourceIngestionJob).filter(SourceIngestionJob.tenant_id == tenant_id).all():
        source_job_models_by_run[str(job.run_id)].append(job)
        source_jobs_by_run[str(job.run_id)].append({
            "id": str(job.id),
            "type": job.job_type,
            "status": job.status,
            "attempt": int(job.attempt or 0),
            "error": _client_job_error(job.job_type, job.last_error),
            "progress": _safe_job_progress(job),
        })
    indexing_jobs_by_run: dict[str, list[dict[str, object]]] = defaultdict(list)
    indexing_job_models_by_run: dict[str, list[IndexingJob]] = defaultdict(list)
    for job in db.query(IndexingJob).filter(IndexingJob.tenant_id == tenant_id).all():
        run_id = str(((job.payload or {}).get("source_metadata") or {}).get("ingestion_run_id") or "")
        if run_id:
            indexing_job_models_by_run[run_id].append(job)
            indexing_jobs_by_run[run_id].append({
                "id": str(job.id),
                "type": "document_indexing",
                "status": job.status,
                "attempt": int(job.attempt_count or 0),
                "error": "Document indexing failed" if job.last_error else None,
            })
    categories = _category_rows(db, tenant_id)
    confirmations = db.query(OnboardingConfirmation).filter(OnboardingConfirmation.tenant_id == tenant_id).all()
    confirmation_map = {row.requirement_key: row for row in confirmations}

    optional_missing = [
        category["key"] for category in categories
        if category["mandatory_group"] is None and category["status"] == "missing"
    ]

    profile_missing = []
    if not profile:
        profile_missing = ["company_name", "timezone", "industry"]
    else:
        profile_missing = [field for field in ("company_name", "timezone", "industry") if not getattr(profile, field, None)]

    readiness = evaluate_readiness(categories, confirmation_map, profile_missing)
    missing_groups = list(readiness["missing_groups"])
    confirmations_needed = list(readiness["confirmations_needed"])
    important_missing = [
        {"requirement": key, "acceptable_categories": list(MANDATORY_GROUPS[key])}
        for key in missing_groups
    ]

    return {
        "step": "knowledge_review",
        "progress": {
            "profile_complete": not profile_missing,
            "sources_connected": len(sources),
            "runs_active": sum(run.status in {"queued", "running", "retrying", "processing"} for run in runs),
            "categories_found": sum(category["status"] == "found" for category in categories),
            "categories_total": len(categories),
        },
        "sources": [
            {
                "id": str(source.id), "name": source.name, "type": source.source_type,
                "status": source.status, "config": source.config,
            }
            for source in sources
        ],
        "runs": [
            {
                "id": str(run.id), "source_id": str(run.source_id), "status": run.status,
                "stage": _run_stage(
                    run,
                    source_job_models_by_run.get(str(run.id), []),
                    indexing_job_models_by_run.get(str(run.id), []),
                ),
                "terminal": run.status in TERMINAL_RUN_STATUSES,
                "progress_percent": _run_progress_percent(
                    run,
                    source_job_models_by_run.get(str(run.id), []),
                    indexing_job_models_by_run.get(str(run.id), []),
                ),
                "page_count": run.page_count, "document_count": run.document_count,
                "error": "Knowledge ingestion failed" if run.error else None,
                "status_url": f"/api/v1/onboarding/runs/{run.id}",
                "events_url": f"/api/v1/onboarding/runs/{run.id}/events",
                "jobs": [
                    *source_jobs_by_run.get(str(run.id), []),
                    *indexing_jobs_by_run.get(str(run.id), []),
                ],
            }
            for run in runs[:20]
        ],
        "category_summaries": categories,
        "missing_data": {"profile": profile_missing, "optional": optional_missing},
        "important_missing_data": important_missing,
        "confirmations_needed": confirmations_needed,
        "confirmations": [
            {
                "requirement": row.requirement_key, "resolution": row.resolution,
                "note": row.note, "confirmed_at": row.confirmed_at.isoformat(),
            }
            for row in confirmations
        ],
        "can_continue": readiness["can_continue"],
        "ready_for_autonomous_actions": readiness["ready_for_autonomous_actions"],
    }
