"""Project indexed facts/chunks into compact, adaptive UI category summaries."""
from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.knowledge.document import DocumentChunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.ingestion import CategorySummary
from app.services.knowledge.categories import (
    CATEGORY_DEFINITIONS,
    canonical_taxonomy_key,
    fact_types_for_category,
    review_mode_for_category,
)
from app.services.knowledge.llm_service import get_llm_service


class SummaryLLM(Protocol):
    def generate(self, prompt: str, stream: bool = True): ...


_FREE_TEXT_KEYS = {
    "id", "sku", "url", "name", "title", "question", "description",
    "summary", "value", "content", "text", "details",
}
_REVIEWED_STATUSES = {"approved", "edited", "rejected"}


def _brief(payload: dict[str, Any]) -> str:
    for key in ("name", "title", "question", "summary", "description", "value", "tier"):
        value = payload.get(key)
        if value:
            return str(value).strip()[:180]
    return json.dumps(payload, default=str, ensure_ascii=False)[:180]


def _numeric_breakdown(key: str, values: list[float]) -> list[dict[str, Any]]:
    if len(values) < 4 or min(values) == max(values):
        return []
    ordered = sorted(values)
    cuts = sorted({ordered[len(ordered) // 4], ordered[len(ordered) // 2], ordered[(len(ordered) * 3) // 4]})
    if not cuts:
        return []
    counts: Counter[str] = Counter()
    for value in values:
        lower = None
        for cut in cuts:
            if value <= cut:
                label = f"{key} <= {cut:g}" if lower is None else f"{lower:g} < {key} <= {cut:g}"
                counts[label] += 1
                break
            lower = cut
        else:
            counts[f"{key} > {cuts[-1]:g}"] += 1
    return [{"label": label, "count": count} for label, count in counts.items()]


def infer_breakdown(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer a useful grouping field from the extracted schema, not industry names."""
    if not payloads:
        return []
    total = len(payloads)
    categorical: list[tuple[float, str, Counter[str]]] = []
    numeric: list[tuple[float, str, list[float]]] = []
    keys = {key for payload in payloads for key in payload}
    for key in keys:
        if key.lower() in _FREE_TEXT_KEYS:
            continue
        raw = [payload.get(key) for payload in payloads if payload.get(key) not in (None, "", [], {})]
        if len(raw) < max(2, math.ceil(total * 0.35)):
            continue
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in raw):
            semantic_bonus = 0.25 if any(token in key.lower() for token in ("price", "cost", "amount", "premium", "value")) else 0.0
            numeric.append((len(raw) / total + semantic_bonus, key, [float(value) for value in raw]))
            continue
        if not all(isinstance(value, (str, bool, int, float)) for value in raw):
            continue
        counts = Counter(str(value).strip() for value in raw if len(str(value).strip()) <= 80)
        if 2 <= len(counts) <= min(25, max(2, total // 2)):
            coverage = sum(counts.values()) / total
            categorical.append((coverage - (len(counts) / max(total, 1)) * 0.1, key, counts))
    if categorical:
        _, _, counts = max(categorical, key=lambda item: (item[0], item[1]))
        return [
            {"label": label, "count": count}
            for label, count in counts.most_common(10)
        ]
    if numeric:
        _, key, values = max(numeric, key=lambda item: (item[0], item[1]))
        return _numeric_breakdown(key, values)
    return []


def _fallback_summary(label: str, count: int, breakdown: list[dict[str, Any]]) -> str:
    suffix = ""
    if breakdown:
        suffix = f" across {len(breakdown)} {label.lower()} groupings"
    return f"{count:,} {label.lower()} records found{suffix}."


def _json_from_model(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Aggregate summary response must be an object")
    return value


async def _generate_aggregate_summaries(llm: SummaryLLM, inputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    prompt = (
        "Create compact onboarding review summaries from these extracted category statistics. "
        "Return strict JSON only as {\"categories\":[{\"key\":str,\"summary\":str,"
        "\"breakdown\":[{\"label\":str,\"count\":int}],\"sample_items\":[str]}]}. "
        "Each summary must be 1-2 sentences. Preserve the supplied counts, use the inferred "
        "breakdown when present, and return 3-5 representative sample items. Never invent items.\n\n"
        + json.dumps(inputs, ensure_ascii=False, default=str)
    )
    text = "".join([part async for part in llm.generate(prompt, stream=False)])
    parsed = _json_from_model(text)
    rows = parsed.get("categories", [])
    return {
        str(row["key"]): row
        for row in rows
        if isinstance(row, dict) and row.get("key") and row.get("summary")
    }


def _run_summary_generation(llm: SummaryLLM, inputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_generate_aggregate_summaries(llm, inputs))
    # This writer is intentionally synchronous because it owns a synchronous
    # SQLAlchemy session. Async callers should run it in their worker thread.
    return {}


def _valid_breakdown(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows = [
        {"label": str(row["label"])[:120], "count": max(0, int(row["count"]))}
        for row in value[:10]
        if isinstance(row, dict) and row.get("label") is not None and isinstance(row.get("count"), (int, float))
    ]
    return rows or None


def _valid_samples(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        allowed = set(fallback)
        rows = [str(item).strip()[:180] for item in value if str(item).strip() in allowed]
        if len(rows) >= 3:
            return rows[:5]
    return fallback[:5]


def refresh_category_summaries(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    llm_service: SummaryLLM | None = None,
) -> None:
    """Materialize fixed-size state rows after extraction completes.

    Aggregate-mode LLM failure is non-fatal: deterministic inferred statistics
    remain available and ingestion is not rolled back because a review summary
    provider is temporarily unavailable.
    """
    settings = get_settings()
    facts: dict[str, list[BusinessFactDraft]] = defaultdict(list)
    confidence: dict[str, list[float]] = defaultdict(list)
    for fact in db.query(BusinessFactDraft).filter(BusinessFactDraft.tenant_id == tenant_id).all():
        try:
            key = canonical_taxonomy_key(fact.fact_type)
        except ValueError:
            continue
        facts[key].append(fact)
        if fact.extraction_confidence is not None:
            confidence[key].append(float(fact.extraction_confidence))

    chunk_evidence: dict[str, list[str]] = defaultdict(list)
    for chunk in db.query(DocumentChunk).filter(DocumentChunk.tenant_id == tenant_id).all():
        raw_key = chunk.detected_category or chunk.primary_category
        if not raw_key:
            continue
        try:
            key = canonical_taxonomy_key(raw_key)
        except ValueError:
            continue
        chunk_evidence[key].append(chunk.content.strip().replace("\n", " ")[:180])

    existing = {
        row.category_key: row
        for row in db.query(CategorySummary).filter(CategorySummary.tenant_id == tenant_id).all()
    }
    aggregate_inputs: list[dict[str, Any]] = []
    aggregate_rows: dict[str, CategorySummary] = {}
    for definition in CATEGORY_DEFINITIONS:
        row = existing.get(definition.key)
        if row is None:
            row = CategorySummary(
                tenant_id=tenant_id,
                category_key=definition.key,
                category_group=definition.group,
            )
            db.add(row)
        category_facts = facts[definition.key]
        payloads = [dict(fact.payload or {}) for fact in category_facts]
        item_values = [_brief(payload) for payload in payloads]
        supporting_chunks = [value for value in chunk_evidence[definition.key] if value]
        values = item_values or supporting_chunks
        row.category_group = definition.group
        # Reviewable counts always correspond to records the items endpoint can
        # return. Chunks alone are supporting evidence, not synthetic items.
        row.item_count = len(category_facts)
        row.status = "found" if category_facts else ("partial" if supporting_chunks else "missing")
        row.confidence = mean(confidence[definition.key]) if confidence[definition.key] else None
        row.needs_review = bool(values) and (
            not confidence[definition.key] or float(row.confidence or 0) < 0.75
        )
        row.reviewed_count = sum(
            (fact.item_review_status or "pending") in _REVIEWED_STATUSES
            for fact in category_facts
        )
        row.display_mode = review_mode_for_category(
            definition.key,
            row.item_count,
            threshold=settings.ENUMERABLE_THRESHOLD,
        )
        if row.display_mode == "aggregate" and values:
            inferred = infer_breakdown(payloads)
            samples = values[:5]
            row.breakdown = inferred
            row.sample_items = samples
            row.summary = _fallback_summary(definition.label, row.item_count, inferred)
            aggregate_rows[definition.key] = row
            aggregate_inputs.append({
                "key": definition.key,
                "label": definition.label,
                "item_count": row.item_count,
                "inferred_breakdown": inferred,
                "representative_items": samples,
            })
        else:
            row.breakdown = []
            row.sample_items = []
            row.summary = "; ".join(values[:3]) if values else None

    if aggregate_inputs:
        service = llm_service
        if service is None and settings.MISTRAL_API_KEY:
            service = get_llm_service(settings)
        if service is not None:
            try:
                generated = _run_summary_generation(service, aggregate_inputs)
            except Exception:
                generated = {}
            for key, generated_row in generated.items():
                row = aggregate_rows.get(key)
                if row is None:
                    continue
                row.summary = str(generated_row.get("summary", row.summary)).strip()[:1000]
                row.breakdown = _valid_breakdown(generated_row.get("breakdown")) or row.breakdown
                row.sample_items = _valid_samples(generated_row.get("sample_items"), row.sample_items)
    db.commit()


def refresh_review_progress(db: Session, tenant_id: uuid.UUID, category_key: str) -> None:
    """Update one materialized counter after an item review action."""
    canonical = canonical_taxonomy_key(category_key)
    reviewed = db.query(func.count(BusinessFactDraft.id)).filter(
        BusinessFactDraft.tenant_id == tenant_id,
        BusinessFactDraft.fact_type.in_(fact_types_for_category(canonical)),
        BusinessFactDraft.item_review_status.in_(_REVIEWED_STATUSES),
    ).scalar() or 0
    row = db.query(CategorySummary).filter(
        CategorySummary.tenant_id == tenant_id,
        CategorySummary.category_key == canonical,
    ).first()
    if row is not None:
        row.reviewed_count = reviewed
        db.commit()
