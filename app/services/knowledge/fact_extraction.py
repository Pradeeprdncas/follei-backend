"""Extract tenant business facts from indexed chunks into a human-review queue."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.knowledge.fact_draft import BusinessFactDraft

FACT_TYPES = {
    "product", "service", "pricing", "policy", "faq", "competitor",
    "customer_segment", "sales_process", "support_process", "payment_process",
}
_settings = get_settings()


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
    category = (document.category or "general").lower()
    chunk = chunks[0]
    text = chunk.text.strip()
    title = Path(document.title).stem or "Untitled business document"
    payload_by_category = {
        "pricing": ("pricing", {"name": title, "model_type": "documented", "tiers": [{"source_text": text[:1800]}]}),
        "policy": ("policy", {"title": chunk.heading or title, "body": text[:4000], "policy_type": "documented"}),
        "faq": ("faq", {"question": chunk.heading or title, "answer": text[:4000]}),
        "catalog": ("product", {"name": chunk.heading or title, "description": text[:4000]}),
        "sop": ("sales_process", {"name": chunk.heading or title, "description": text[:4000]}),
    }
    match = payload_by_category.get(category)
    if not match:
        return []
    fact_type, payload = match
    return [{"fact_type": fact_type, "payload": payload, "chunk": chunk, "confidence": 0.55}]


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
    if not facts:
        facts = _fallback_facts(document, chunk_list)

    drafts: list[BusinessFactDraft] = []
    for fact in facts:
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

