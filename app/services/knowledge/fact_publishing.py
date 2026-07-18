"""Publish reviewed business-fact drafts into approved PostgreSQL entities."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import Competitor, FAQ, Policy, PricingModel, Procedure, Product, Service
from app.models.knowledge.fact_draft import BusinessFactDraft


def _citation_metadata(draft: BusinessFactDraft) -> dict[str, Any]:
    return {"fact_draft_id": str(draft.id), "source_citation": draft.citation}


def _text(payload: dict[str, Any], name: str, default: str = "") -> str:
    value = payload.get(name, default)
    return value if isinstance(value, str) else str(value)


_FLAT_TIER_FIELDS = ("tier", "price", "currency", "billing_frequency", "billing_term")


def _normalize_pricing_tiers(payload: dict[str, Any]) -> list[Any]:
    """Return a tiers list from either extraction payload shape.

    The deterministic fallback extractor emits {"tiers": [...]}, but the LLM
    extractor (the path real documents go through) emits a flat single-tier
    payload instead: {"tier": "Enterprise", "price": 999,
    "billing_frequency": "monthly", "billing_term": "annually"} — no "tiers"
    key at all. Reading only payload["tiers"] silently drops that data.
    """
    tiers = payload.get("tiers")
    if isinstance(tiers, list) and tiers:
        return tiers
    flat = {key: payload[key] for key in _FLAT_TIER_FIELDS if payload.get(key) is not None}
    if not flat:
        return []
    if "tier" in flat:
        flat["name"] = flat.pop("tier")
    return [flat]


def publish_fact_draft(db: Session, draft: BusinessFactDraft) -> object:
    """Create the approved operational record. Caller owns the final commit."""
    if draft.approval_status != "draft":
        raise ValueError("Only draft facts can be published")
    payload = draft.payload or {}
    metadata = _citation_metadata(draft)
    tenant_id = draft.tenant_id

    if draft.fact_type == "product":
        record = Product(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed product"), sku=payload.get("sku"), description=payload.get("description"), metadata_=metadata)
    elif draft.fact_type == "service":
        record = Service(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed service"), description=payload.get("description"), metadata_=metadata)
    elif draft.fact_type == "pricing":
        record = PricingModel(tenant_id=tenant_id, name=_text(payload, "name", "Documented pricing"), model_type=_text(payload, "model_type", "documented"), tiers=_normalize_pricing_tiers(payload), metadata_=metadata)
    elif draft.fact_type == "policy":
        record = Policy(tenant_id=tenant_id, title=_text(payload, "title", "Documented policy"), body=payload.get("body"), policy_type=payload.get("policy_type"), metadata_=metadata)
    elif draft.fact_type == "faq":
        # FAQ has no metadata column. The draft remains the immutable citation record.
        record = FAQ(tenant_id=tenant_id, question=_text(payload, "question", "Documented question"), answer=_text(payload, "answer"), tags=[f"fact_draft:{draft.id}"])
    elif draft.fact_type == "competitor":
        record = Competitor(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed competitor"), website=payload.get("website"), summary=payload.get("summary"), metadata_=metadata)
    elif draft.fact_type in {"sales_process", "support_process", "payment_process"}:
        steps = payload.get("steps", [])
        record = Procedure(tenant_id=tenant_id, title=_text(payload, "name", _text(payload, "title", "Documented process")), steps=steps if isinstance(steps, list) else [], metadata_={**metadata, "process_type": draft.fact_type, "description": payload.get("description")})
    else:
        raise ValueError(f"Fact type {draft.fact_type!r} is reviewable but has no approved operational publisher")

    db.add(record)
    db.flush()
    draft.published_record_type = record.__tablename__
    draft.published_record_id = record.id
    return record
