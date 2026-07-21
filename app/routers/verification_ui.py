"""Authenticated System 1/2 verification consoles.

The pages in this router are thin views over the production ingestion, storage,
retrieval, and voice paths.  They intentionally do not maintain a second copy
of knowledge or fabricate demo metrics.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config.database import get_db
from app.config.ferretdb import get_context_database
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id
from app.models.conversations.conversation import Conversation
from app.models.leads.lead import Lead
from app.models.tenancy import User

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


@router.get("/tenant", include_in_schema=False)
def tenant_console() -> FileResponse:
    return FileResponse(_STATIC / "tenant_console.html")


@router.get("/user", include_in_schema=False)
def user_console() -> FileResponse:
    return FileResponse(_STATIC / "user_console.html")


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
    structured: dict[str, int] = {}
    for label, table_name in structured_tables.items():
        structured[label] = int(
            db.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}).scalar() or 0
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


@router.post("/ui/user/session")
def create_user_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a real lead and conversation inside the authenticated tenant."""
    lead = Lead(
        id=uuid4(), tenant_id=current_user.tenant_id,
        email=f"voice-{uuid4().hex[:12]}@local.follei",
        first_name=current_user.first_name or "Voice", last_name="User",
        company="Follei voice console",
    )
    db.add(lead)
    db.flush()
    conversation = Conversation(
        id=uuid4(), tenant_id=current_user.tenant_id, lead_id=lead.id,
        title="Voice console", channel="voice", status="active",
        started_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    return {
        "tenant_id": str(current_user.tenant_id),
        "lead_id": str(lead.id),
        "conversation_id": str(conversation.id),
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
