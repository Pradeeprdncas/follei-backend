"""Tenant-safe FerretDB reasoning context access."""
import re
from datetime import datetime, timezone
from typing import Any
from app.config.ferretdb import get_context_database


def get_context(*, tenant_id: str, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    row = get_context_database()["tenant_context"].find_one(
        {"tenant_id": str(tenant_id), "subject_type": subject_type, "subject_id": str(subject_id)},
        {"_id": 0},
    )
    return row


def upsert_context(*, tenant_id: str, subject_type: str, subject_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge `updates` into this subject's FerretDB reasoning context, creating it if absent.

    This is the write side of get_context(). Until now nothing ever wrote to
    `tenant_context`, so build_agent_context()'s customer_context was always
    empty for every lead/customer — the read path existed, the write path
    didn't. Callers (e.g. accumulate_lead_qualification in
    learned_bant_service.py) use this to carry BANT/MEDDIC evidence and other
    per-lead facts forward across turns/sessions instead of losing them the
    moment the conversation moves on.
    """
    collection = get_context_database()["tenant_context"]
    now = datetime.now(timezone.utc).isoformat()
    collection.update_one(
        {"tenant_id": str(tenant_id), "subject_type": subject_type, "subject_id": str(subject_id)},
        {"$set": {
            **updates,
            "tenant_id": str(tenant_id),
            "subject_type": subject_type,
            "subject_id": str(subject_id),
            "updated_at": now,
        }},
        upsert=True,
    )
    return get_context(tenant_id=tenant_id, subject_type=subject_type, subject_id=subject_id) or {}


def search_document_memory(*, tenant_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return relevant clean document-memory projections for one tenant only."""
    stopwords = {"the", "and", "for", "from", "what", "which", "does", "with", "according", "contain"}
    query_terms = {
        token for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) >= 3 and token not in stopwords
    }
    if not query_terms:
        return []
    rows = get_context_database()["knowledge_document_memory"].find(
        {"tenant_id": str(tenant_id)}, {"_id": 0}
    ).limit(100)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        searchable = " ".join([
            str(row.get("title") or ""), str(row.get("category") or ""),
            str(row.get("summary") or ""), " ".join(row.get("keywords") or []),
        ]).lower()
        matched = sorted(term for term in query_terms if term in searchable)
        if not matched:
            continue
        ranked.append({**row, "matched_terms": matched, "score": len(matched) / len(query_terms)})
    ranked.sort(key=lambda item: (-float(item["score"]), str(item.get("title") or "")))
    return ranked[:max(1, min(int(limit), 10))]
