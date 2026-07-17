"""Tenant-scoped, fixed-order agent context with trust, freshness, and conflicts."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.rag.retrieval.dense import retrieve_dense
from app.services.knowledge.context_store import get_context
from app.services.knowledge.graph import traverse_graph

# Lower number is more authoritative. Agents receive this provenance rather than
# silently treating semantically similar data as equally trustworthy.
SOURCE_TRUST = {"postgres": 1, "graph": 2, "qdrant": 3, "ferret": 4}


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            return None
    return None


def _freshness_score(value: Any) -> float:
    """Return 0..1 recency weight; missing dates are intentionally weakest."""
    timestamp = _as_datetime(value)
    if not timestamp:
        return 0.0
    age_days = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400)
    return round(1 / (1 + age_days / 365), 4)


def _decorate(item: dict[str, Any], *, source: str, updated_at: Any = None) -> dict[str, Any]:
    decorated = dict(item)
    timestamp = updated_at or decorated.get("updated_at") or decorated.get("created_at") or decorated.get("observed_at") or decorated.get("last_seen_at")
    decorated["source"] = source
    decorated["trust_rank"] = SOURCE_TRUST[source]
    decorated["freshness_score"] = _freshness_score(timestamp)
    decorated["freshness_at"] = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    return decorated


def _rank(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (item.get("trust_rank", 99), -float(item.get("freshness_score", 0)), -float(item.get("score", 0) or 0)))


def _value_signature(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return str(value or "").strip().lower()


def _conflicts(approved_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag disagreeing approved PostgreSQL facts; never choose one invisibly."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in approved_facts:
        if fact.get("source") != "postgres" or not fact.get("approved", False):
            continue
        key = (str(fact.get("fact_type") or "fact"), str(fact.get("topic") or "").strip().lower())
        if key[1]:
            grouped.setdefault(key, []).append(fact)
    conflicts: list[dict[str, Any]] = []
    for (fact_type, topic), candidates in grouped.items():
        signatures = {_value_signature(candidate.get("value")) for candidate in candidates}
        if len(candidates) > 1 and len(signatures) > 1:
            ranked = _rank(candidates)
            conflicts.append({
                "type": "approved_fact_conflict",
                "fact_type": fact_type,
                "topic": topic,
                "requires_review": True,
                "reason": "Multiple approved PostgreSQL facts disagree; no value was selected automatically.",
                "candidates": [{
                    "fact_id": str(item.get("fact_id") or item.get("id") or ""),
                    "value": item.get("value"),
                    "freshness_at": item.get("freshness_at"),
                    "freshness_score": item.get("freshness_score"),
                    "citation": item.get("citation"),
                } for item in ranked],
            })
    return conflicts


def _query_matches(query: str, *values: Any) -> bool:
    terms = {term for term in re.findall(r"[\w-]{3,}", query.lower()) if term not in {"what", "does", "have", "with", "about", "tell", "please"}}
    if not terms:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return any(term in haystack for term in terms)


def _approved_operational_facts(db: Session, tenant_id: str, query: str) -> list[dict[str, Any]]:
    """Read only human-approved structured records from PostgreSQL."""
    try:
        from app.models.domain import FAQ, Policy, PricingModel, Product, Service
        models = (
            (PricingModel, "pricing", "name", "tiers"),
            (Policy, "policy", "title", "body"),
            (Product, "product", "name", "description"),
            (Service, "service", "name", "description"),
            (FAQ, "faq", "question", "answer"),
        )
        facts: list[dict[str, Any]] = []
        for model, fact_type, topic_attr, value_attr in models:
            rows = db.query(model).filter(model.tenant_id == tenant_id).order_by(model.updated_at.desc() if hasattr(model, "updated_at") else model.created_at.desc()).limit(30).all()
            for row in rows:
                topic, value = getattr(row, topic_attr), getattr(row, value_attr)
                if not _query_matches(query, topic, value, fact_type):
                    continue
                metadata = getattr(row, "metadata_", {}) or {}
                citation = metadata.get("source_citation") or {"fact_draft_id": metadata.get("fact_draft_id")}
                facts.append(_decorate({
                    "fact_id": str(row.id), "fact_type": fact_type, "topic": str(topic), "value": value,
                    "approved": True, "citation": citation,
                }, source="postgres", updated_at=getattr(row, "updated_at", None) or getattr(row, "created_at", None)))
        return _rank(facts)
    except Exception:
        # Approved facts enrich agents but a partial operational schema must not block a response.
        return []


def load_postgres_context(db: Session, tenant_id: str, lead_id: str | None, query: str = "") -> tuple[dict, list[dict]]:
    facts: dict[str, Any] = {"tenant_id": str(tenant_id), "approved": _approved_operational_facts(db, str(tenant_id), query)}
    relationships: list[dict] = []
    if not lead_id:
        return facts, relationships
    try:
        from app.models.leads.lead import Lead
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    except Exception:
        lead = None
    if lead:
        facts["lead"] = {"id": str(lead.id), "name": " ".join(filter(None, [lead.first_name, lead.last_name])), "email": lead.email, "status": lead.status, "revenue_score": lead.revenue_score, "current_score": lead.current_score, "current_temperature": lead.current_temperature}
        if lead.company:
            relationships.append(_decorate({"from": str(lead.id), "relation": "belongs_to", "to": lead.company}, source="postgres", updated_at=getattr(lead, "updated_at", None)))
    return facts, relationships


async def build_agent_context(*, db: Session, tenant_id: str, query: str, lead_id: str | None = None, customer_id: str | None = None, top_k: int = 5) -> dict:
    """Only bounded, tenant-scoped, provenance-aware context is exposed to agents."""
    facts, relationships = load_postgres_context(db, str(tenant_id), lead_id)
    graph_relationships = [_decorate(item, source="graph", updated_at=(item.get("citation") or {}).get("updated_at")) for item in traverse_graph(db, tenant_id=str(tenant_id), query=query)]
    relationships = _rank([*relationships, *graph_relationships])
    subject_type = "lead" if lead_id else "customer" if customer_id else "tenant"
    subject_id = lead_id or customer_id or str(tenant_id)
    raw_evidence = await retrieve_dense(query, str(tenant_id), top_k=max(1, min(top_k, 10)))
    evidence = _rank([_decorate(item, source="qdrant") for item in raw_evidence])[:10]
    memory = get_context(tenant_id=str(tenant_id), subject_type=subject_type, subject_id=str(subject_id)) or {}
    customer_context = _decorate(memory, source="ferret", updated_at=memory.get("updated_at")) if memory else {}
    approved = _rank(list(facts.get("approved") or _approved_operational_facts(db, str(tenant_id), query)))
    facts["approved"] = approved
    conflicts = _conflicts(approved)
    citations = [{"chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"), "page": item.get("page"), "heading_path": item.get("heading_path", []), "source_type": item.get("source_type"), "approval_status": item.get("approval_status"), "trust_rank": item.get("trust_rank"), "freshness_at": item.get("freshness_at")} for item in evidence]
    return {
        "facts": facts,
        "relationships": relationships,
        "evidence": evidence,
        "customer_context": customer_context,
        "citations": citations,
        "conflicts": conflicts,
        "trust_policy": {"postgres": 1, "graph": 2, "qdrant": 3, "ferret": 4},
    }