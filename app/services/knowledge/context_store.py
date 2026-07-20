"""Tenant-safe FerretDB reasoning context access."""
import re
from typing import Any
from app.config.ferretdb import get_context_database


def get_context(*, tenant_id: str, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    row = get_context_database()["tenant_context"].find_one(
        {"tenant_id": str(tenant_id), "subject_type": subject_type, "subject_id": str(subject_id)},
        {"_id": 0},
    )
    return row


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
