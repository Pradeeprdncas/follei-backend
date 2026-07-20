"""Publish reviewed business-fact drafts into approved PostgreSQL entities."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import BusinessPlan, Competitor, CustomerSegment, FAQ, Policy, PricingModel, Procedure, Product, Service, SLA
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.fact_extraction import validate_fact_payload


def _citation_metadata(draft: BusinessFactDraft) -> dict[str, Any]:
    return {"fact_draft_id": str(draft.id), "source_citation": draft.citation}


def _text(payload: dict[str, Any], name: str, default: str = "") -> str:
    value = payload.get(name, default)
    return value if isinstance(value, str) else str(value)


_FLAT_TIER_FIELDS = ("tier", "price", "currency", "billing_frequency", "billing_term")


def canonicalize_fact_payload(
    fact_type: str,
    payload: dict[str, Any] | None,
    *,
    fallback_text: str | None = None,
    fallback_title: str | None = None,
) -> dict[str, Any]:
    """Translate supported legacy extraction shapes into the publish schema.

    Early policy extraction emitted ``description`` instead of ``body``.  The
    old publisher read only ``body``, which allowed a reviewed refund policy to
    become an operational row with a NULL body.  Canonicalization lives at the
    publication boundary so every caller, including backfills, gets the same
    validation and mapping.
    """
    canonical = dict(payload or {})
    if fact_type == "policy":
        body = canonical.get("body") or canonical.get("description") or fallback_text
        title = canonical.get("title") or canonical.get("name") or fallback_title
        if body is not None:
            canonical["body"] = str(body).strip()
        if title:
            canonical["title"] = str(title).strip()
        elif canonical.get("body"):
            canonical["title"] = "Documented policy"
    elif fact_type == "sla":
        # The extractor may return either numeric *_hours values or readable
        # commitments such as "2 hours". Preserve the source wording while
        # making the operational target queryable as an integer.
        for source_key, target_key in (
            ("response_target", "response_target_hours"),
            ("resolution_target", "resolution_target_hours"),
        ):
            if canonical.get(target_key) not in (None, ""):
                continue
            source_value = canonical.get(source_key)
            if isinstance(source_value, (int, float)):
                canonical[target_key] = int(source_value)
                continue
            match = re.search(r"\b(\d+)\s*(?:business\s+)?hours?\b", str(source_value or ""), re.I)
            if match:
                canonical[target_key] = int(match.group(1))
    return canonical


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
    citation = draft.citation or {}
    payload = canonicalize_fact_payload(
        draft.fact_type,
        draft.payload,
        fallback_title=citation.get("heading"),
    )
    validation_error = validate_fact_payload(draft.fact_type, payload)
    if validation_error:
        raise ValueError(f"Invalid {draft.fact_type} draft: {validation_error}")
    # Reassign the JSON value so the reviewed, publishable shape is itself
    # durable and future repairs never have to reinterpret it again.
    draft.payload = payload
    metadata = _citation_metadata(draft)
    tenant_id = draft.tenant_id

    if draft.fact_type == "product":
        record = Product(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed product"), sku=payload.get("sku"), description=payload.get("description"), metadata_=metadata)
    elif draft.fact_type == "service":
        record = Service(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed service"), description=payload.get("description"), metadata_=metadata)
    elif draft.fact_type == "pricing":
        record = PricingModel(tenant_id=tenant_id, name=_text(payload, "name", "Documented pricing"), model_type=_text(payload, "model_type", "documented"), tiers=_normalize_pricing_tiers(payload), metadata_=metadata)
    elif draft.fact_type == "plan":
        pricing = payload.get("pricing") or {key: payload[key] for key in _FLAT_TIER_FIELDS if payload.get(key) is not None}
        record = BusinessPlan(tenant_id=tenant_id, name=_text(payload, "name", _text(payload, "tier", "Documented plan")), description=payload.get("description"), pricing=pricing, metadata_=metadata)
    elif draft.fact_type == "policy":
        record = Policy(tenant_id=tenant_id, title=_text(payload, "title", "Documented policy"), body=payload.get("body"), policy_type=payload.get("policy_type"), metadata_=metadata)
    elif draft.fact_type == "sla":
        record = SLA(
            tenant_id=tenant_id,
            name=_text(payload, "name", "Documented SLA"),
            description=payload.get("description"),
            response_target_hours=payload.get("response_target_hours"),
            resolution_target_hours=payload.get("resolution_target_hours"),
            coverage=payload.get("coverage"),
            metadata_=metadata,
        )
    elif draft.fact_type == "faq":
        # FAQ has no metadata column. The draft remains the immutable citation record.
        record = FAQ(tenant_id=tenant_id, question=_text(payload, "question", "Documented question"), answer=_text(payload, "answer"), tags=[f"fact_draft:{draft.id}"])
    elif draft.fact_type == "competitor":
        record = Competitor(tenant_id=tenant_id, name=_text(payload, "name", "Unnamed competitor"), website=payload.get("website"), summary=payload.get("summary"), metadata_=metadata)
    elif draft.fact_type == "customer_segment":
        record = CustomerSegment(tenant_id=tenant_id, name=_text(payload, "name", "Documented customer segment"), description=payload.get("description"), criteria=payload.get("criteria") or {}, metadata_=metadata)
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
