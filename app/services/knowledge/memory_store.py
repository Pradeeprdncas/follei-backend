"""FerretDB write-side customer/lead memory with recency and short fact history."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.config.ferretdb import get_context_database

_MEMORY_FIELDS = ("pain_points", "budget_signals", "timeline", "stakeholders", "objections", "preferences", "competitors", "requirements")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _fallback_facts(summary: str) -> dict[str, list[str]]:
    result = {field: [] for field in _MEMORY_FIELDS}
    for match in re.findall(r"(?:budget|cost)\D{0,30}(\$?\s?[\d,]+(?:k|k\b)?)", summary, flags=re.I):
        result["budget_signals"].append(f"budget {match.strip()}")
    for name in ("Salesforce", "HubSpot", "Zoho", "Freshworks", "Microsoft", "SAP"):
        if name.lower() in summary.lower():
            result["competitors"].append(name)
    return result


def upsert_summary_memory(*, tenant_id: str, subject_type: str, subject_id: str, summary_id: str, conversation_id: str, structured: dict[str, Any] | None, summary_text: str, confidence: float = 0.7) -> dict[str, Any]:
    """Idempotently merge summary facts and keep recent historical observations."""
    collection = get_context_database()["tenant_context"]
    key = {"tenant_id": str(tenant_id), "subject_type": subject_type, "subject_id": str(subject_id)}
    existing = collection.find_one(key, {"_id": 0}) or {}
    applied = existing.get("applied_summary_ids", [])
    if str(summary_id) in applied:
        return existing
    structured = structured or {}
    fallback = _fallback_facts(summary_text)
    now = _now()
    history = list(existing.get("history", []))[-99:]
    document = {**existing, **key, "version": int(existing.get("version", 0)) + 1, "updated_at": now, "applied_summary_ids": (applied + [str(summary_id)])[-50:]}
    for field in _MEMORY_FIELDS:
        incoming = _values(structured.get(field)) or fallback[field]
        current = list(existing.get(field, []))
        by_value = {str(item.get("value", "")).lower(): item for item in current if isinstance(item, dict)}
        for value in incoming:
            normalized = value.lower()
            fact = by_value.get(normalized)
            if fact:
                fact.update({"last_seen_at": now, "confidence": max(float(fact.get("confidence", 0)), confidence), "occurrences": int(fact.get("occurrences", 1)) + 1, "source_summary_id": str(summary_id)})
            else:
                fact = {"value": value, "confidence": confidence, "observed_at": now, "last_seen_at": now, "occurrences": 1, "source_summary_id": str(summary_id), "conversation_id": str(conversation_id)}
                current.append(fact)
                history.append({"field": field, **fact})
        document[field] = current[-30:]
    document["history"] = history[-100:]
    collection.replace_one(key, document, upsert=True)
    return document


def upsert_document_memory(
    *,
    tenant_id: str,
    document_id: str,
    title: str,
    source_type: str,
    category: str | None,
    version: int,
    summary: str,
    keywords: list[str],
    chunk_count: int,
    source_uri: str | None = None,
    previous_document_id: str | None = None,
) -> dict[str, Any]:
    """Write the clean long-term-memory projection for one indexed document.

    PostgreSQL remains the canonical document/fact store and Qdrant owns chunk
    embeddings.  FerretDB receives only a compact, queryable memory record so
    an upload is represented in all three stores without copying raw blobs or
    creating a second source of truth.
    """
    collection = get_context_database()["knowledge_document_memory"]
    key = {"tenant_id": str(tenant_id), "document_id": str(document_id)}
    document = {
        **key,
        "title": str(title),
        "source_type": str(source_type),
        "category": str(category) if category else None,
        "version": int(version),
        "summary": str(summary or "").strip(),
        "keywords": [str(value).strip() for value in keywords if str(value).strip()],
        "chunk_count": int(chunk_count),
        "source_uri": str(source_uri) if source_uri else None,
        "previous_document_id": str(previous_document_id) if previous_document_id else None,
        "projection_type": "indexed_document_summary",
        "canonical_store": "postgres",
        "semantic_store": "qdrant",
        "updated_at": _now(),
    }
    collection.replace_one(key, document, upsert=True)
    return document


def seed_onboarding_context(*, tenant_id: str, industry: str | None, goals: list[str], contact_channels: list[str]) -> dict[str, Any]:
    """One-time seed of the tenant-level FerretDB context record from onboarding answers.

    New: unlike upsert_summary_memory (which only ever writes lead/customer
    subjects from conversation summaries), nothing previously wrote the
    tenant-level subject at all. build_agent_context() already falls back to
    subject_type="tenant"/subject_id=tenant_id when there's no lead_id or
    customer_id, so seeding that same key here gives agents industry/goal/
    channel context from day one instead of an empty customer_context until
    the first conversation is summarized.
    """
    collection = get_context_database()["tenant_context"]
    key = {"tenant_id": str(tenant_id), "subject_type": "tenant", "subject_id": str(tenant_id)}
    existing = collection.find_one(key, {"_id": 0}) or {}
    document = {
        **existing,
        **key,
        "industry": industry,
        "goals": goals,
        "contact_channels": contact_channels,
        "seeded_from": "onboarding",
        "updated_at": _now(),
    }
    collection.replace_one(key, document, upsert=True)
    return document
