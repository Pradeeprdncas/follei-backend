"""FerretDB write-side customer/lead memory with recency and short fact history."""
from __future__ import annotations

import json
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
    source_metadata: dict[str, Any] | None = None,
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
        "source_metadata": dict(source_metadata or {}),
        "lead_ids": [str(value) for value in (source_metadata or {}).get("lead_ids", [])],
        "lead_import_job_ids": [str(value) for value in (source_metadata or {}).get("lead_import_job_ids", [])],
        "lead_import_row_ids": [str(value) for value in (source_metadata or {}).get("lead_import_row_ids", [])],
        "projection_type": "indexed_document_summary",
        "canonical_store": "postgres",
        "semantic_store": "qdrant",
        "updated_at": _now(),
    }
    collection.replace_one(key, document, upsert=True)
    return document


def upsert_category_document_projection(*, tenant_id: str, document_id: str, document_version_id: str | None, workspace_id: str | None, title: str, primary_category: str | None, secondary_categories: list[str], summary: str, sections: list[dict[str, Any]], entities: list[dict[str, Any]], source_revision: int, source_metadata: dict[str, Any] | None = None) -> None:
    """Write rebuildable ordered document/entity projections from outbox data."""
    database = get_context_database()
    key = {"tenant_id": str(tenant_id), "document_id": str(document_id)}
    metadata = dict(source_metadata or {})
    database["knowledge_document_views"].replace_one(key, {**key, "document_version_id": document_version_id, "workspace_id": workspace_id, "title": title, "primary_category": primary_category, "secondary_categories": secondary_categories, "summary": summary, "status": "processed", "sections": sections, "source_metadata": metadata, "lead_ids": [str(value) for value in metadata.get("lead_ids", [])], "lead_import_job_ids": [str(value) for value in metadata.get("lead_import_job_ids", [])], "lead_import_row_ids": [str(value) for value in metadata.get("lead_import_row_ids", [])], "sync": {"source_revision": source_revision, "projection_version": 1, "projected_at": _now()}}, upsert=True)
    collection = database["knowledge_entities"]
    for entity in entities:
        entity_key = {"tenant_id": str(tenant_id), "entity_id": str(entity["entity_id"])}
        collection.replace_one(entity_key, {**entity_key, "workspace_id": workspace_id, "document_id": str(document_id), "document_version_id": document_version_id, **entity, "metadata": {"source_revision": source_revision, "projection_version": 1, "projected_at": _now()}}, upsert=True)


def upsert_lead_import_memory(*, tenant_id: str, lead_id: str, import_job_id: str | None, record: dict[str, Any]) -> dict[str, Any]:
    """Persist the complete imported record as tenant-scoped lead memory.

    Postgres keeps the operational lead fields; this projection deliberately
    retains unmapped columns and provenance so no CSV/document information is
    silently discarded during normalization.
    """
    collection = get_context_database()["lead_import_memory"]
    key = {"tenant_id": str(tenant_id), "lead_id": str(lead_id)}
    existing = collection.find_one(key, {"_id": 0}) or {}
    now = _now()
    imports = list(existing.get("imports", []))
    source = {"import_job_id": str(import_job_id) if import_job_id else None, "record": record, "stored_at": now}
    if not any(item.get("import_job_id") == source["import_job_id"] for item in imports):
        imports.append(source)
    document = {**existing, **key, "projection_type": "lead_import_raw_record", "canonical_store": "postgres", "imports": imports[-20:], "latest_record": record, "updated_at": now}
    collection.replace_one(key, document, upsert=True)
    return document


def upsert_crm_record_memory(*, tenant_id: str, crm_record_id: str, provider: str, object_type: str, external_id: str, source_revision: int, normalized: dict[str, Any], raw: dict[str, Any], lead_id: str | None = None, customer_id: str | None = None) -> dict[str, Any]:
    """Store the variable provider payload while PostgreSQL remains canonical."""
    collection = get_context_database()["crm_record_memory"]
    key = {"tenant_id": str(tenant_id), "provider": provider, "object_type": object_type, "external_id": str(external_id)}
    document = {
        **key,
        "crm_record_id": str(crm_record_id),
        "lead_id": str(lead_id) if lead_id else None,
        "customer_id": str(customer_id) if customer_id else None,
        "source_revision": int(source_revision),
        "normalized": dict(normalized or {}),
        "raw": dict(raw or {}),
        "projection_type": "crm_provider_record",
        "canonical_store": "postgres",
        "semantic_store": "qdrant",
        "updated_at": _now(),
    }
    collection.replace_one(key, document, upsert=True)
    return document


def append_lead_nurture_turn(
    *,
    tenant_id: str,
    lead_id: str,
    conversation_id: str,
    turn_id: str,
    user_text: str,
    assistant_text: str,
    channel: str = "chat",
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Immediately mirror a complete nurturing exchange into FerretDB.

    PostgreSQL remains canonical through Conversation + Message rows. This
    bounded projection makes both sides of every turn available to the next
    tailored response without waiting for the periodic conversation summary.
    """
    collection = get_context_database()["tenant_context"]
    key = {
        "tenant_id": str(tenant_id),
        "subject_type": "lead",
        "subject_id": str(lead_id),
    }
    existing = collection.find_one(key, {"_id": 0}) or {}
    history = list(existing.get("nurture_history", []))
    if any(str(item.get("turn_id")) == str(turn_id) for item in history):
        return existing
    now = _now()
    history.append({
        "turn_id": str(turn_id),
        "conversation_id": str(conversation_id),
        "channel": channel,
        "user": str(user_text),
        "assistant": str(assistant_text),
        "citations": json.loads(json.dumps(list(citations or [])[:20], default=str)),
        "at": now,
    })
    document = {
        **existing,
        **key,
        "projection_type": "lead_nurturing_memory",
        "canonical_store": "postgres",
        "nurture_history": history[-100:],
        "last_nurture_turn": history[-1],
        "nurture_turn_count": int(existing.get("nurture_turn_count", len(history) - 1)) + 1,
        "updated_at": now,
    }
    collection.replace_one(key, document, upsert=True)
    return document


def append_lead_flow_event(*, tenant_id: str, lead_id: str, enrollment_id: str, node_key: str, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mirror a bounded, readable flow timeline while Postgres stays canonical."""
    collection = get_context_database()["tenant_context"]
    key = {"tenant_id": str(tenant_id), "subject_type": "lead", "subject_id": str(lead_id)}
    existing = collection.find_one(key, {"_id": 0}) or {}
    history = list(existing.get("flow_history", []))
    event_id = f"{enrollment_id}:{node_key}:{event_type}:{(data or {}).get('attempt', 1)}"
    if any(item.get("event_id") == event_id for item in history):
        return existing
    history.append({"event_id": event_id, "enrollment_id": str(enrollment_id), "node_key": node_key, "event_type": event_type, "data": json.loads(json.dumps(data or {}, default=str)), "at": _now()})
    document = {**existing, **key, "flow_history": history[-200:], "last_flow_event": history[-1], "updated_at": _now()}
    collection.replace_one(key, document, upsert=True)
    return document


def upsert_workflow_override_memory(*, tenant_id: str, workflow_instance_id: str, flow_version_id: str, version: int, overrides: dict[str, Any]) -> dict[str, Any]:
    """Project tenant-editable workflow wording/layout while Postgres stays canonical."""
    collection = get_context_database()["workflow_override_memory"]
    key = {"tenant_id": str(tenant_id), "workflow_instance_id": str(workflow_instance_id)}
    document = {
        **key,
        "flow_version_id": str(flow_version_id),
        "version": int(version),
        "overrides": json.loads(json.dumps(overrides or {}, default=str)),
        "projection_type": "tenant_workflow_override",
        "canonical_store": "postgres",
        "updated_at": _now(),
    }
    collection.replace_one(key, document, upsert=True)
    return document


def append_lead_outbound_event(
    *,
    tenant_id: str,
    lead_id: str,
    conversation_id: str,
    message_id: str,
    content: str,
    channel: str,
    subject: str | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Mirror a one-sided outbound touch while PostgreSQL remains canonical."""
    collection = get_context_database()["tenant_context"]
    key = {
        "tenant_id": str(tenant_id),
        "subject_type": "lead",
        "subject_id": str(lead_id),
    }
    existing = collection.find_one(key, {"_id": 0}) or {}
    events = list(existing.get("outbound_history", []))
    if any(str(item.get("message_id")) == str(message_id) for item in events):
        return existing
    events.append({
        "message_id": str(message_id),
        "conversation_id": str(conversation_id),
        "campaign_id": str(campaign_id) if campaign_id else None,
        "channel": channel,
        "subject": subject,
        "content": str(content),
        "at": _now(),
    })
    document = {
        **existing,
        **key,
        "projection_type": existing.get("projection_type") or "lead_nurturing_memory",
        "canonical_store": "postgres",
        "outbound_history": events[-100:],
        "last_outbound_event": events[-1],
        "outbound_event_count": int(existing.get("outbound_event_count", len(events) - 1)) + 1,
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
