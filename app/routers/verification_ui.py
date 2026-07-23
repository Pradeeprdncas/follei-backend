"""Authenticated System 1/2 verification consoles.

The pages in this router are thin views over the production ingestion, storage,
retrieval, and voice paths.  They intentionally do not maintain a second copy
of knowledge or fabricate demo metrics.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config.database import get_db
from app.config.ferretdb import get_context_database
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id
from app.models.conversations.conversation import Conversation
from app.domains.lead_import.models import LeadImportJob, LeadImportRow
from app.models.leads.lead import Lead
from app.models.knowledge.indexing_job import IndexingJob
from app.models.tenancy import User
from app.services.knowledge.context_store import get_context

router = APIRouter(tags=["System verification UI"])
_STATIC = Path(__file__).resolve().parent.parent / "static"
_settings = get_settings()


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _mapping_rows(result: Any) -> list[dict[str, Any]]:
    return [{key: _iso(value) for key, value in row._mapping.items()} for row in result]


_SECRET_KEY_PARTS = ("authorization", "password", "secret", "api_key", "apikey", "credential", "access_token", "refresh_token")


def _safe_store_value(value: Any, *, key: str = "") -> Any:
    """Make store records JSON-safe without leaking credentials in the inspector."""
    normalized_key = key.lower().replace("-", "_")
    if normalized_key and any(part in normalized_key for part in _SECRET_KEY_PARTS):
        return "[redacted]"
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, dict):
        return {str(item_key): _safe_store_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_store_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_session_identifier(value: str) -> str:
    """Canonicalize equivalent email/phone forms to one stable lead key."""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if "@" in normalized:
        return normalized.lower()
    digits = re.sub(r"\D", "", normalized)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[-10:]
    return digits or normalized.lower()


def _merge_voice_session_memory(*, tenant_id: str, canonical_lead_id: str, alias_ids: list[str]) -> None:
    """Preserve old voice memory/vector evidence while consolidating lead aliases."""
    if not alias_ids:
        return
    try:
        collection = get_context_database()["tenant_context"]
        key = {"tenant_id": tenant_id, "subject_type": "lead", "subject_id": canonical_lead_id}
        canonical = collection.find_one(key, {"_id": 0}) or key
        aliases = list(collection.find({"tenant_id": tenant_id, "subject_type": "lead", "subject_id": {"$in": alias_ids}}, {"_id": 0}))
        for field in ("bant", "meddic"):
            scores = dict(canonical.get(field) or {})
            for record in aliases:
                for name, value in (record.get(field) or {}).items():
                    scores[name] = max(float(scores.get(name, 0) or 0), float(value or 0))
            if scores:
                canonical[field] = scores
        for field in ("requirements", "qualification_history", "history"):
            combined = list(canonical.get(field) or [])
            seen = {str(item) for item in combined}
            for record in aliases:
                for item in record.get(field) or []:
                    if str(item) not in seen:
                        combined.append(item); seen.add(str(item))
            if combined:
                canonical[field] = combined[-100:]
        canonical["merged_subject_ids"] = sorted(set(canonical.get("merged_subject_ids") or []) | set(alias_ids))
        canonical["updated_at"] = datetime.utcnow().isoformat()
        collection.replace_one(key, canonical, upsert=True)
        collection.update_many(
            {"tenant_id": tenant_id, "subject_type": "lead", "subject_id": {"$in": alias_ids}},
            {"$set": {"merged_into": canonical_lead_id}},
        )
    except Exception:
        pass
    try:
        client = get_qdrant()
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=_settings.QDRANT_COLLECTION_NAME,
                scroll_filter=Filter(must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                    FieldCondition(key="lead_id", match=MatchAny(any=alias_ids)),
                ]),
                limit=256, offset=offset, with_payload=False, with_vectors=False,
            )
            if points:
                client.set_payload(
                    collection_name=_settings.QDRANT_COLLECTION_NAME,
                    points=[point.id for point in points],
                    payload={"lead_id": canonical_lead_id, "merged_lead_ids": alias_ids},
                )
            if offset is None:
                break
    except Exception:
        pass


@router.get("/tenant", include_in_schema=False)
def tenant_console() -> FileResponse:
    return FileResponse(_STATIC / "tenant_console.html")


@router.get("/user", include_in_schema=False)
def user_console() -> FileResponse:
    return FileResponse(_STATIC / "user_console.html")


@router.get("/status", include_in_schema=False)
def status_console() -> FileResponse:
    return FileResponse(_STATIC / "status.html")


def _qdrant_documents(tenant_id: str) -> tuple[dict[str, dict[str, Any]], str | None]:
    by_document: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"point_count": 0, "approval_statuses": set(), "source_types": set(), "categories": set()}
    )
    try:
        client = get_qdrant()
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=_settings.QDRANT_COLLECTION_NAME,
                scroll_filter=Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                document_id = str(payload.get("document_id") or "")
                if not document_id:
                    continue
                item = by_document[document_id]
                item["point_count"] += 1
                if payload.get("approval_status"):
                    item["approval_statuses"].add(str(payload["approval_status"]))
                if payload.get("source_type"):
                    item["source_types"].add(str(payload["source_type"]))
                category = payload.get("category")
                if not category:
                    category = next((str(tag).split(":", 1)[1] for tag in payload.get("tags", []) if str(tag).startswith("category:")), None)
                if category:
                    item["categories"].add(str(category))
            if offset is None:
                break
        normalized = {
            document_id: {
                **item,
                "approval_statuses": sorted(item["approval_statuses"]),
                "source_types": sorted(item["source_types"]),
                "categories": sorted(item["categories"]),
            }
            for document_id, item in by_document.items()
        }
        return normalized, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _ferret_documents(tenant_id: str) -> tuple[dict[str, dict[str, Any]], str | None]:
    try:
        rows = list(
            get_context_database()["knowledge_document_memory"]
            .find({"tenant_id": tenant_id}, {"_id": 0})
            .sort("updated_at", -1)
            .limit(250)
        )
        return {str(row["document_id"]): row for row in rows if row.get("document_id")}, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


@router.get("/ui/tenant/snapshot")
def tenant_snapshot(
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Show tenant-scoped, read-only evidence from each knowledge store."""
    documents = _mapping_rows(
        db.execute(
            text(
                """
                SELECT d.id, d.public_id, d.title, d.source_type, d.category, d.version,
                       d.status, d.summary, d.keywords, d.created_at, d.indexed_at,
                       COUNT(c.id)::int AS chunk_count
                FROM documents d
                LEFT JOIN document_chunks c ON c.document_id = d.id
                WHERE d.tenant_id = :tenant_id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                LIMIT 100
                """
            ),
            {"tenant_id": tenant_id},
        )
    )
    jobs = _mapping_rows(
        db.execute(
            text(
                """
                SELECT id, document_id, status, disposition, attempt_count, last_error,
                       created_at, completed_at
                FROM indexing_jobs WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC LIMIT 30
                """
            ),
            {"tenant_id": tenant_id},
        )
    )
    graph = _mapping_rows(
        db.execute(
            text(
                """
                SELECT r.id, s.name AS source, s.entity_type AS source_type,
                       r.relation_type, t.name AS target, t.entity_type AS target_type,
                       r.confidence, r.created_at
                FROM entity_relations r
                JOIN entities s ON s.id = r.source_entity_id
                JOIN entities t ON t.id = r.target_entity_id
                WHERE r.tenant_id = :tenant_id
                ORDER BY r.created_at DESC LIMIT 100
                """
            ),
            {"tenant_id": tenant_id},
        )
    )
    structured_tables = {
        "products": "products", "services": "services", "pricing": "pricing_models",
        "policies": "policies", "plans": "business_plans", "slas": "slas",
        "faqs": "faqs", "competitors": "competitors", "customer_segments": "customer_segments",
    }
    structured: dict[str, int] = {}
    for label, table_name in structured_tables.items():
        structured[label] = int(
            db.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}).scalar() or 0
        )
    # Sales/support/payment processes share one table (Procedure), distinguished
    # by metadata_->>'process_type' (see fact_publishing.py) rather than three
    # separate tables — count each slice explicitly so they show up as their
    # own System-1 categories instead of being invisible inside "procedures".
    for process_type, label in (
        ("sales_process", "sales_processes"),
        ("support_process", "support_processes"),
        ("payment_process", "payment_processes"),
    ):
        structured[label] = int(
            db.execute(
                text("SELECT COUNT(*) FROM procedures WHERE tenant_id = :tenant_id AND metadata->>'process_type' = :process_type"),
                {"tenant_id": tenant_id, "process_type": process_type},
            ).scalar() or 0
        )

    qdrant, qdrant_error = _qdrant_documents(tenant_id)
    ferret, ferret_error = _ferret_documents(tenant_id)
    rows = []
    for document in documents:
        document_id = str(document["id"])
        vector = qdrant.get(document_id)
        memory = ferret.get(document_id)
        ready = document.get("status") in {"ready", "indexed", "completed"}
        rows.append({
            "document": {**document, "id": document_id},
            "postgres": {"present": True, "chunk_count": document.get("chunk_count", 0)},
            "qdrant": {"present": bool(vector), **(vector or {"point_count": 0, "approval_statuses": [], "source_types": [], "categories": []})},
            "ferretdb": {"present": bool(memory), **(memory or {})},
            "consistent": bool(ready and vector and memory),
            "pending": not ready,
        })

    return {
        "tenant_id": tenant_id,
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "postgres_documents": len(documents),
            "postgres_chunks": sum(int(row.get("chunk_count") or 0) for row in documents),
            "qdrant_points": sum(int(row.get("point_count") or 0) for row in qdrant.values()),
            "ferretdb_documents": len(ferret),
            "ready_in_all_three": sum(1 for row in rows if row["consistent"]),
            "job_statuses": dict(Counter(str(job["status"]) for job in jobs)),
            "structured": structured,
            "graph_edges": len(graph),
        },
        "documents": rows,
        "jobs": jobs,
        "graph": graph,
        "store_errors": {"qdrant": qdrant_error, "ferretdb": ferret_error},
        "store_roles": {
            "postgres": "Canonical documents, chunks, approved structured facts, and graph",
            "qdrant": "Semantic vectors for approved tenant-scoped retrieval",
            "ferretdb": "Clean long-term document and conversation memory projections",
        },
    }


@router.get("/ui/tenant/store-content")
def tenant_store_content(
    document_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return bounded, tenant-scoped content samples from all three stores.

    Qdrant vectors are deliberately excluded. The useful semantic payload is
    shown, while credential-shaped fields are redacted recursively.
    """
    params: dict[str, Any] = {"tenant_id": tenant_id, "limit": limit}
    document_clause = ""
    if document_id is not None:
        params["document_id"] = str(document_id)
        document_clause = "AND d.id = CAST(:document_id AS uuid)"

    postgres_chunks = _mapping_rows(
        db.execute(
            text(
                f"""
                SELECT c.id, c.document_id, d.title AS document_title, c.chunk_index,
                       c.content, c.token_count, c.metadata, c.created_at
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.tenant_id = CAST(:tenant_id AS uuid) {document_clause}
                ORDER BY d.created_at DESC, c.chunk_index ASC
                LIMIT :limit
                """
            ),
            params,
        )
    )

    structured_facts: list[dict[str, Any]] = []
    if document_id is None:
        for label, table_name in {
            "product": "products", "service": "services", "pricing": "pricing_models",
            "policy": "policies", "plan": "business_plans", "sla": "slas",
            "faq": "faqs", "competitor": "competitors", "customer_segment": "customer_segments",
        }.items():
            records = db.execute(
                text(
                    f"SELECT id::text AS id, to_jsonb(row_data) - 'tenant_id' AS record "
                    f"FROM {table_name} row_data WHERE tenant_id = CAST(:tenant_id AS uuid) "
                    "ORDER BY id LIMIT 5"
                ),
                {"tenant_id": tenant_id},
            ).mappings()
            structured_facts.extend(
                {"record_type": label, "id": row["id"], "record": _safe_store_value(row["record"])}
                for row in records
            )
        # Sales/support/payment processes all live in one Procedure table,
        # distinguished by metadata_->>'process_type' -- see fact_publishing.py.
        for process_type, label in (
            ("sales_process", "sales_process"),
            ("support_process", "support_process"),
            ("payment_process", "payment_process"),
        ):
            records = db.execute(
                text(
                    "SELECT id::text AS id, to_jsonb(row_data) - 'tenant_id' AS record "
                    "FROM procedures row_data WHERE tenant_id = CAST(:tenant_id AS uuid) "
                    "AND metadata->>'process_type' = :process_type ORDER BY id LIMIT 5"
                ),
                {"tenant_id": tenant_id, "process_type": process_type},
            ).mappings()
            structured_facts.extend(
                {"record_type": label, "id": row["id"], "record": _safe_store_value(row["record"])}
                for row in records
            )

    qdrant_records: list[dict[str, Any]] = []
    qdrant_error = None
    try:
        conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if document_id is not None:
            conditions.append(FieldCondition(key="document_id", match=MatchValue(value=str(document_id))))
        points, _ = get_qdrant().scroll(
            collection_name=_settings.QDRANT_COLLECTION_NAME,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        qdrant_records = [
            {"point_id": str(point.id), "payload": _safe_store_value(point.payload or {})}
            for point in points
        ]
    except Exception as exc:
        qdrant_error = f"{type(exc).__name__}: {exc}"

    ferret_records: list[dict[str, Any]] = []
    ferret_error = None
    try:
        context_db = get_context_database()
        document_filter: dict[str, Any] = {"tenant_id": tenant_id}
        if document_id is not None:
            document_filter["document_id"] = str(document_id)
        document_memory = list(
            context_db["knowledge_document_memory"]
            .find(document_filter, {"_id": 0})
            .sort("updated_at", -1)
            .limit(limit)
        )
        ferret_records.extend(
            {"collection": "knowledge_document_memory", "record": _safe_store_value(row)}
            for row in document_memory
        )
        if document_id is None:
            tenant_memory = list(
                context_db["tenant_context"]
                .find({"tenant_id": tenant_id}, {"_id": 0})
                .limit(limit)
            )
            ferret_records.extend(
                {"collection": "tenant_context", "record": _safe_store_value(row)}
                for row in tenant_memory
            )
    except Exception as exc:
        ferret_error = f"{type(exc).__name__}: {exc}"

    return {
        "tenant_id": tenant_id,
        "document_id": str(document_id) if document_id else None,
        "limit": limit,
        "postgres": {
            "chunks": [_safe_store_value(row) for row in postgres_chunks],
            "structured_facts": structured_facts,
        },
        "qdrant": {"points": qdrant_records, "vectors_included": False, "error": qdrant_error},
        "ferretdb": {"records": ferret_records, "error": ferret_error},
    }


@router.get("/ui/tenant/leads")
def tenant_leads(
    limit: int = Query(default=100, ge=1, le=200),
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List this tenant's leads, newest-analyzed first, for the /tenant console's per-lead verification view."""
    candidates = (
        db.query(Lead)
        .filter(Lead.tenant_id == tenant_id)
        .order_by(Lead.last_analysis_at.desc().nullslast(), Lead.created_at.desc())
        .limit(400)
        .all()
    )
    leads = [lead for lead in candidates if not (lead.profile_data or {}).get("merged_into")][:limit]
    return {
        "tenant_id": tenant_id,
        "leads": [
            {
                "id": str(lead.id),
                "public_id": lead.public_id,
                "email": lead.email,
                "name": " ".join(filter(None, [lead.first_name, lead.last_name])) or None,
                "company": lead.company,
                "status": lead.status,
                "current_score": lead.current_score,
                "current_temperature": lead.current_temperature,
                "last_analysis_at": _iso(lead.last_analysis_at),
                "created_at": _iso(lead.created_at),
            }
            for lead in leads
        ],
    }


@router.get("/ui/tenant/leads/{lead_id}")
def tenant_lead_detail(
    lead_id: UUID,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Everything Follei knows about one lead, for per-lead verification.

    Combines the Postgres Lead row, their recent conversations, and their
    FerretDB qualification memory (BANT/MEDDIC/history) -- the same
    tenant_context document build_agent_context() feeds into chat_pipeline()
    to tailor replies, so this is a direct way to see what a reply for this
    lead is actually being generated with.
    """
    lead = db.query(Lead).filter(Lead.id == str(lead_id), Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found for this tenant")

    conversations = _mapping_rows(
        db.execute(
            text(
                """
                SELECT id, public_id, title, channel, status, message_count,
                       current_lead_temperature, started_at, last_activity_at
                FROM conversations
                WHERE tenant_id = :tenant_id AND lead_id = :lead_id
                ORDER BY started_at DESC LIMIT 25
                """
            ),
            {"tenant_id": tenant_id, "lead_id": str(lead_id)},
        )
    )

    memory = get_context(tenant_id=tenant_id, subject_type="lead", subject_id=str(lead_id))

    # Import rows deliberately keep the source/extracted data separate from the
    # operational Lead columns.  This lets the console prove that an imported
    # field has not been silently discarded during normalisation.
    import_rows = (
        db.query(LeadImportRow)
        .filter(LeadImportRow.tenant_id == tenant_id, LeadImportRow.lead_id == lead.id)
        .order_by(LeadImportRow.created_at.desc())
        .all()
    )
    import_job_ids = {str(row.job_id) for row in import_rows}
    import_jobs = (
        db.query(LeadImportJob)
        .filter(LeadImportJob.tenant_id == tenant_id, LeadImportJob.id.in_([row.job_id for row in import_rows]))
        .all()
        if import_rows
        else []
    )

    import_memory = None
    import_memory_error = None
    crawled_memory: list[dict[str, Any]] = []
    try:
        context_database = get_context_database()
        import_memory = context_database["lead_import_memory"].find_one(
            {"tenant_id": str(tenant_id), "lead_id": str(lead.id)}, {"_id": 0}
        )
        summaries = list(context_database["knowledge_document_memory"].find(
            {"tenant_id": str(tenant_id), "lead_ids": str(lead.id)}, {"_id": 0}
        ).limit(50))
        views = {
            str(row.get("document_id")): row
            for row in context_database["knowledge_document_views"].find(
                {"tenant_id": str(tenant_id), "lead_ids": str(lead.id)}, {"_id": 0}
            ).limit(50)
        }
        crawled_memory = [
            {**summary, "document_view": views.get(str(summary.get("document_id")))}
            for summary in summaries
        ]
    except Exception as exc:
        import_memory_error = f"{type(exc).__name__}: {exc}"

    qdrant_evidence: list[dict[str, Any]] = []
    qdrant_error = None
    try:
        points, _ = get_qdrant().scroll(
            collection_name=_settings.QDRANT_COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id))),
                ],
                should=[
                    FieldCondition(key="lead_id", match=MatchValue(value=str(lead.id))),
                    FieldCondition(key="lead_ids", match=MatchAny(any=[str(lead.id)])),
                ],
            ),
            limit=20,
            with_payload=True,
            with_vectors=False,
        )
        qdrant_evidence = [
            {"point_id": str(point.id), "payload": _safe_store_value(point.payload or {})}
            for point in points
        ]
    except Exception as exc:
        qdrant_error = f"{type(exc).__name__}: {exc}"

    # A URL crawl creates ordinary indexing jobs, with a reference to the
    # import job in its payload.  Filter in Python for portable JSON support
    # across the project's PostgreSQL and test database configurations.
    linked_ingestion_jobs = [
        job
        for job in db.query(IndexingJob).filter(IndexingJob.tenant_id == tenant_id).order_by(IndexingJob.created_at.desc()).limit(200).all()
        if str((job.payload or {}).get("lead_import_job_id") or "") in import_job_ids
        and (not (job.payload or {}).get("lead_ids") or str(lead.id) in {str(value) for value in (job.payload or {}).get("lead_ids", [])})
    ][:50]

    return {
        "tenant_id": tenant_id,
        "lead": {
            "id": str(lead.id),
            "public_id": lead.public_id,
            "email": lead.email,
            "name": " ".join(filter(None, [lead.first_name, lead.last_name])) or None,
            "company": lead.company,
            "status": lead.status,
            "current_score": lead.current_score,
            "current_temperature": lead.current_temperature,
            "analysis_confidence": lead.analysis_confidence,
            "profile_data": _safe_store_value(lead.profile_data or {}),
            "last_analysis_at": _iso(lead.last_analysis_at),
            "created_at": _iso(lead.created_at),
        },
        "conversations": conversations,
        "ferretdb_memory": _safe_store_value(memory) if memory else None,
        "ferretdb_import_memory": _safe_store_value(import_memory) if import_memory else None,
        "ferretdb_import_memory_error": import_memory_error,
        "ferretdb_crawled_documents": _safe_store_value(crawled_memory),
        "import_rows": [
            {
                "id": str(row.id),
                "job_id": str(row.job_id),
                "row_index": row.row_index,
                "status": row.status,
                "confidence": row.confidence,
                "match_reason": row.match_reason,
                "raw_data": _safe_store_value(row.raw_data or {}),
                "normalized_data": _safe_store_value(row.normalized_data or {}),
                "extracted_data": _safe_store_value(row.extracted_data or {}),
            }
            for row in import_rows
        ],
        "import_jobs": [
            {
                "id": str(job.id),
                "filename": job.filename,
                "file_type": job.file_type,
                "status": job.status,
                "statistics": _safe_store_value(job.statistics or {}),
                "created_at": _iso(job.created_at),
                "completed_at": _iso(job.completed_at),
            }
            for job in import_jobs
        ],
        "qdrant_evidence": qdrant_evidence,
        "qdrant_evidence_error": qdrant_error,
        "linked_ingestion_jobs": [
            {
                "id": str(job.id),
                "document_id": str(job.document_id) if job.document_id else None,
                "status": job.status,
                "disposition": job.disposition,
                "source_uri": (job.payload or {}).get("source_uri"),
                "filename": (job.payload or {}).get("filename"),
                "last_error": job.last_error,
                "created_at": _iso(job.created_at),
            }
            for job in linked_ingestion_jobs
        ],
    }


class UserSessionRequest(BaseModel):
    """`identifier` is the lead's own phone number or email, entered on /user —
    not the admin's login. It's the stable key that lets a returning lead be
    recognized: matching it to an existing Lead reuses that lead_id, which is
    also the FerretDB tenant_context subject_id, so their prior BANT/MEDDIC
    evidence and conversation history are picked up automatically by
    build_agent_context() on the very next turn instead of starting cold.
    """
    identifier: str | None = None


def _consolidate_legacy_voice_leads(db: Session, *, user: User, canonical: Lead) -> list[str]:
    """Repoint legacy anonymous console sessions without deleting their audit rows."""
    aliases = (
        db.query(Lead)
        .filter(
            Lead.tenant_id == user.tenant_id,
            Lead.id != canonical.id,
            Lead.company == "Follei voice console",
            Lead.first_name == (user.first_name or "Voice"),
            Lead.email.like("voice-%@local.follei"),
            ~Lead.email.like("voice-user-%@local.follei"),
        )
        .all()
    )
    alias_ids = [str(lead.id) for lead in aliases if not (lead.profile_data or {}).get("merged_into")]
    if not alias_ids:
        return []
    reference_tables = (
        "conversations", "customers", "inbound_emails", "lead_import_rows",
        "learning_signals", "campaign_messages", "lead_scores",
    )
    # Keep a reversible audit map on every alias before repointing its rows.
    for alias in aliases:
        if str(alias.id) not in alias_ids:
            continue
        references: dict[str, list[str]] = {}
        for table_name in reference_tables:
            record_ids = db.execute(
                text(f"SELECT id::text FROM {table_name} WHERE lead_id = :lead_id"),
                {"lead_id": str(alias.id)},
            ).scalars().all()
            if record_ids:
                references[table_name] = list(record_ids)
        alias.profile_data = {
            **(alias.profile_data or {}),
            "merged_into": str(canonical.id),
            "merged_reason": "legacy_voice_session",
            "merged_reference_ids": references,
        }
    for table_name in reference_tables:
        db.execute(
            text(f"UPDATE {table_name} SET lead_id = :canonical_id WHERE lead_id = ANY(CAST(:alias_ids AS uuid[]))"),
            {"canonical_id": str(canonical.id), "alias_ids": alias_ids},
        )
    canonical.profile_data = {
        **(canonical.profile_data or {}),
        "session_owner_user_id": str(user.id),
        "merged_lead_ids": sorted(set((canonical.profile_data or {}).get("merged_lead_ids") or []) | set(alias_ids)),
    }
    db.flush()
    return alias_ids


@router.post("/ui/user/session")
def create_user_session(
    payload: UserSessionRequest = Body(default=UserSessionRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create (or resume) a lead and start a new conversation for it.

    Stores whatever the visitor types — phone or email — in Lead.email: that
    column is a plain unvalidated String here (this console never enforces
    email format), so it works as a single lookup key for either identifier
    without needing the awkward Integer Lead.phone column.
    """
    requested_identifier = _normalize_session_identifier(payload.identifier or "")
    identifier = requested_identifier
    returning_lead = False
    lead: Lead | None = None
    if identifier:
        candidates = db.query(Lead).filter(Lead.tenant_id == current_user.tenant_id).limit(500).all()
        lead = next(
            (
                candidate for candidate in candidates
                if not (candidate.profile_data or {}).get("merged_into")
                and (
                    _normalize_session_identifier(candidate.email) == identifier
                    or (identifier.isdigit() and candidate.phone and str(candidate.phone) == identifier)
                )
            ),
            None,
        )
        returning_lead = lead is not None

    if not identifier:
        # A blank identity in the authenticated voice console belongs to the
        # same signed-in tester. Prefer their existing explicit console lead;
        # otherwise use a deterministic per-user identifier.
        lead = (
            db.query(Lead)
            .filter(
                Lead.tenant_id == current_user.tenant_id,
                Lead.company == "Follei voice console",
                Lead.first_name == (current_user.first_name or "Voice"),
                ~Lead.email.like("voice-%@local.follei"),
            )
            .order_by(Lead.last_analysis_at.desc().nullslast(), Lead.created_at.desc())
            .first()
        )
        if lead and not (lead.profile_data or {}).get("merged_into"):
            identifier = lead.email
            returning_lead = True
        else:
            lead = None
            identifier = f"voice-user-{current_user.id}@local.follei"
            lead = db.query(Lead).filter(Lead.tenant_id == current_user.tenant_id, Lead.email == identifier).first()
            returning_lead = lead is not None

    if lead is None:
        parsed_phone = int(identifier) if identifier.isdigit() and len(identifier) <= 15 else 0
        phone_value = parsed_phone if parsed_phone <= 2_147_483_647 else 0
        lead = Lead(
            id=uuid4(), tenant_id=current_user.tenant_id,
            email=identifier,
            first_name=current_user.first_name or "Voice", last_name="User",
            company="Follei voice console", phone=phone_value,
            profile_data={"session_owner_user_id": str(current_user.id), "session_identifier": identifier},
        )
        db.add(lead)
        db.flush()

    alias_ids = _consolidate_legacy_voice_leads(db, user=current_user, canonical=lead)

    conversation = Conversation(
        id=uuid4(), tenant_id=current_user.tenant_id, lead_id=lead.id,
        title="Voice console", channel="voice", status="active",
        started_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    _merge_voice_session_memory(
        tenant_id=str(current_user.tenant_id),
        canonical_lead_id=str(lead.id),
        alias_ids=alias_ids,
    )
    return {
        "tenant_id": str(current_user.tenant_id),
        "lead_id": str(lead.id),
        "conversation_id": str(conversation.id),
        "returning_lead": returning_lead,
        "canonical_identifier": identifier,
        "merged_legacy_sessions": len(alias_ids),
    }


@router.get("/ui/user/capabilities")
def user_capabilities(tenant_id: str = Depends(get_authenticated_tenant_id)) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "speech_to_text": {"provider": _settings.SPEECH_TO_TEXT_PROVIDER, "model": _settings.ELEVENLABS_STT_MODEL, "configured": bool(_settings.ELEVENLABS_API_KEY)},
        "text_to_speech": {"provider": "elevenlabs", "model": _settings.ELEVENLABS_TTS_MODEL, "configured": bool(_settings.ELEVENLABS_API_KEY and _settings.ELEVENLABS_VOICE_ID)},
        "analysis": {
            "scores": ["ICP", "Intent", "Engagement", "Qualification", "Buying Signal", "Relationship"],
            "voice_enrichment": ["Relationship", "overall lead confidence", "emotion fusion"],
            "transcript_business_signals": ["ICP", "Intent", "Engagement", "Qualification", "Buying Signal"],
            "qualification": ["BANT", "MEDDIC"],
            "qualification_input": "transcript and conversation context; voice tone is not required",
            "implementation": "Follei-adapted lead-intelligence pipeline derived from the audited external repository family",
        },
    }
