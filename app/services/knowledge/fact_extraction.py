"""Extract tenant business facts from indexed chunks into a human-review queue."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.services.knowledge.categories import fact_type_for_category

FACT_TYPES = {
    "product", "service", "pricing", "plan", "policy", "sla", "faq", "competitor",
    "customer_segment", "sales_process", "support_process", "payment_process",
}
_settings = get_settings()


def _nonempty(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    return isinstance(value, str) and bool(value.strip())


def validate_fact_payload(fact_type: str, payload: dict[str, Any]) -> str | None:
    """Return a reviewer-visible schema error, or None for publishable drafts.

    The LLM output is deliberately treated as untrusted input.  These compact
    per-type rules reject incomplete records early instead of letting a review
    click create a misleading operational record.
    """
    if fact_type in {"product", "service", "competitor", "customer_segment"} and not _nonempty(payload, "name"):
        return f"{fact_type} requires a name"
    if fact_type == "pricing":
        tiers = payload.get("tiers")
        flat_price = payload.get("price")
        has_tier_price = isinstance(tiers, list) and any(isinstance(tier, dict) and tier.get("price") not in (None, "") for tier in tiers)
        if not has_tier_price and flat_price in (None, ""):
            return "pricing requires a price"
    elif fact_type == "plan" and not (_nonempty(payload, "name") or _nonempty(payload, "tier")):
        return "plan requires a name or tier"
    elif fact_type == "policy" and (not _nonempty(payload, "title") or not _nonempty(payload, "body")):
        return "policy requires a title and body"
    elif fact_type == "sla":
        if not _nonempty(payload, "name"):
            return "sla requires a name"
        if not (_nonempty(payload, "description") or payload.get("response_target_hours") not in (None, "") or payload.get("resolution_target_hours") not in (None, "")):
            return "sla requires a description or a response/resolution target"
    elif fact_type == "faq" and (not _nonempty(payload, "question") or not _nonempty(payload, "answer")):
        return "faq requires a question and answer"
    elif fact_type in {"sales_process", "support_process", "payment_process"}:
        if not (_nonempty(payload, "name") or _nonempty(payload, "title")):
            return f"{fact_type} requires a name"
        if not (_nonempty(payload, "description") or (isinstance(payload.get("steps"), list) and payload["steps"])):
            return f"{fact_type} requires a description or steps"
    return None


def _citation(document: Any, chunk: Any) -> dict[str, Any]:
    return {
        "document_id": str(document.id),
        "document_name": document.title,
        "chunk_id": str(chunk.id),
        "page": chunk.page,
        "heading": chunk.heading,
        "heading_path": chunk.section_path or [],
        "source_uri": document.source_uri,
        "version": document.version,
    }


def _fallback_facts(document: Any, chunks: list[Any]) -> list[dict[str, Any]]:
    """Safe, deterministic drafts when an LLM is unavailable.

    These drafts deliberately preserve source text for a reviewer instead of
    guessing values such as a price or a legal condition.
    """
    if not chunks:
        return []
    category = fact_type_for_category((getattr(document, "primary_category", None) or document.category or "general").lower())
    # Mixed commercial documents commonly contain policy, price, plan, and FAQ
    # sections.  Produce conservative, directly quoted drafts for each signal
    # instead of letting a single target category hide the rest.
    mixed: list[dict[str, Any]] = []
    for candidate in chunks:
        value = candidate.text.strip()
        heading = candidate.heading or ""
        price = re.search(r"(?:USD\s*|\$)([0-9][0-9,]*(?:\.\d{1,2})?)", value, re.I)
        if price and re.search(r"pricing|price|plan", f"{heading} {value}", re.I):
            mixed.append({"fact_type": "pricing", "payload": {"name": heading or "Documented pricing", "model_type": "documented", "tiers": [{"price": float(price.group(1).replace(',', '')), "source_text": value[:1800]}]}, "chunk": candidate, "confidence": 0.65})
        if re.search(r"enterprise\s+(support\s+)?plan", f"{heading} {value}", re.I):
            mixed.append({"fact_type": "plan", "payload": {"name": "Enterprise Plan", "description": value[:1800]}, "chunk": candidate, "confidence": 0.6})
        if "?" in heading or re.search(r"frequently asked|faq", heading, re.I):
            answer = value.split("\n", 1)[-1].strip()
            if answer:
                mixed.append({"fact_type": "faq", "payload": {"question": heading, "answer": answer[:1800]}, "chunk": candidate, "confidence": 0.6})
        if re.search(r"refund policy|terms|policy", heading, re.I) and value:
            mixed.append({"fact_type": "policy", "payload": {"title": heading, "body": value[:4000], "policy_type": "documented"}, "chunk": candidate, "confidence": 0.6})
    chunk = chunks[0]
    text = chunk.text.strip()
    title = Path(document.title).stem or "Untitled business document"
    price_match = re.search(r"(?:USD\s*|\$)([0-9][0-9,]*(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
    fallback_price = float(price_match.group(1).replace(",", "")) if price_match else None
    payload_by_category = {
        "product": ("product", {"name": chunk.heading or title, "description": text[:4000]}),
        "service": ("service", {"name": chunk.heading or title, "description": text[:4000]}),
        "pricing": ("pricing", {"name": title, "model_type": "documented", "tiers": [{"price": fallback_price, "source_text": text[:1800]}]}),
        "plan": ("plan", {"name": chunk.heading or title, "description": text[:4000]}),
        "policy": ("policy", {"title": chunk.heading or title, "body": text[:4000], "policy_type": "documented"}),
        "sla": ("sla", {"name": chunk.heading or title, "description": text[:4000]}),
        "faq": ("faq", {"question": chunk.heading or title, "answer": text[:4000]}),
        "competitor": ("competitor", {"name": chunk.heading or title, "summary": text[:4000]}),
        "customer_segment": ("customer_segment", {"name": chunk.heading or title, "description": text[:4000], "criteria": {"source_text": text[:1800]}}),
        "sales_process": ("sales_process", {"name": chunk.heading or title, "description": text[:4000]}),
        "support_process": ("support_process", {"name": chunk.heading or title, "description": text[:4000]}),
        "payment_process": ("payment_process", {"name": chunk.heading or title, "description": text[:4000]}),
        "catalog": ("product", {"name": chunk.heading or title, "description": text[:4000]}),
        "sop": ("sales_process", {"name": chunk.heading or title, "description": text[:4000]}),
    }
    match = payload_by_category.get(category)
    if not match:
        return mixed
    fact_type, payload = match
    if not any(item["fact_type"] == fact_type and item["chunk"].id == chunk.id for item in mixed):
        mixed.append({"fact_type": fact_type, "payload": payload, "chunk": chunk, "confidence": 0.55})
    return mixed


def _normalise_facts(raw: Any, chunks: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), list):
        return []
    chunks_by_id = {str(chunk.id): chunk for chunk in chunks}
    facts: list[dict[str, Any]] = []
    for item in raw["facts"]:
        if not isinstance(item, dict):
            continue
        fact_type = str(item.get("fact_type", "")).lower().strip()
        payload = item.get("payload")
        chunk = chunks_by_id.get(str(item.get("source_chunk_id", "")))
        if fact_type not in FACT_TYPES or not isinstance(payload, dict) or chunk is None:
            continue
        if validate_fact_payload(fact_type, payload):
            continue
        confidence = item.get("confidence", 0.5)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5
        facts.append({"fact_type": fact_type, "payload": payload, "chunk": chunk, "confidence": confidence})
    return facts


async def _llm_facts(document: Any, chunks: list[Any]) -> list[dict[str, Any]]:
    if not _settings.MISTRAL_API_KEY:
        return []
    evidence = "\n\n".join(
        f"[chunk_id={chunk.id}; page={chunk.page}; heading={chunk.heading or ''}]\n{chunk.text[:2200]}"
        for chunk in chunks[:12]
    )
    prompt = f"""Extract only directly supported business facts from this tenant document.
Allowed fact_type values: {', '.join(sorted(FACT_TYPES))}.
Payload requirements: product/service/competitor/customer_segment require name;
pricing requires a numeric price (or tiers with price); plan requires name or tier;
policy requires title and body; faq requires question and answer; each process
requires name/title plus description or steps.
Return JSON only: {{"facts":[{{"fact_type":"pricing","payload":{{}},"source_chunk_id":"UUID","confidence":0.0}}]}}.
Do not invent prices, product capabilities, legal terms, or competitors. Every fact must cite one supplied chunk id.
Document: {document.title}; category: {document.category or 'general'}
Evidence:
{evidence}"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 900,
                },
            )
            response.raise_for_status()
        return _normalise_facts(json.loads(response.json()["choices"][0]["message"]["content"]), chunks)
    except Exception as exc:
        logger.warning(f"Fact extraction fell back to deterministic draft: {exc}")
        return []


async def extract_document_facts(db: Session, *, document: Any, chunks: Iterable[Any]) -> list[BusinessFactDraft]:
    """Store draft facts only; publishing to operational tables is a review action."""
    chunk_list = list(chunks)
    facts = await _llm_facts(document, chunk_list)
    # Deterministic extraction is a conservative coverage layer, not merely an
    # outage fallback.  An LLM may correctly return one category while omitting
    # another category that is explicitly present in the same mixed document.
    # Prefer the LLM payload for the same fact type/source chunk and supplement
    # only the missing pairs.
    seen_sources = {
        (fact["fact_type"], str(fact["chunk"].id))
        for fact in facts
    }
    for fallback in _fallback_facts(document, chunk_list):
        source_key = (fallback["fact_type"], str(fallback["chunk"].id))
        if source_key not in seen_sources:
            facts.append(fallback)
            seen_sources.add(source_key)

    drafts: list[BusinessFactDraft] = []
    for fact in facts:
        if validate_fact_payload(fact["fact_type"], fact["payload"]):
            logger.info(f"Skipped incomplete {fact['fact_type']} draft for document={document.id}")
            continue
        exists = db.query(BusinessFactDraft.id).filter(
            BusinessFactDraft.tenant_id == document.tenant_id,
            BusinessFactDraft.document_id == document.id,
            BusinessFactDraft.chunk_id == fact["chunk"].id,
            BusinessFactDraft.fact_type == fact["fact_type"],
            BusinessFactDraft.approval_status == "draft",
        ).first()
        if exists:
            continue
        draft = BusinessFactDraft(
            tenant_id=document.tenant_id,
            document_id=document.id,
            chunk_id=fact["chunk"].id,
            fact_type=fact["fact_type"],
            payload=fact["payload"],
            citation=_citation(document, fact["chunk"]),
            extraction_confidence=fact["confidence"],
            approval_status="draft",
        )
        db.add(draft)
        drafts.append(draft)
    if drafts:
        db.commit()
        for draft in drafts:
            db.refresh(draft)
        logger.info(f"Created {len(drafts)} fact drafts for document={document.id}")
    return drafts

