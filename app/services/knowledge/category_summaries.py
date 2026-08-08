"""Project indexed facts/chunks into compact UI category summaries."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from app.models.knowledge.document import DocumentChunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.ingestion import CategorySummary
from app.services.knowledge.categories import CATEGORY_DEFINITIONS, canonical_taxonomy_key


def _brief(payload: dict) -> str:
    for key in ("name", "title", "question", "summary", "description", "value"):
        value = payload.get(key)
        if value:
            return str(value).strip()[:180]
    return json.dumps(payload, default=str, ensure_ascii=False)[:180]


def refresh_category_summaries(db: Session, tenant_id: uuid.UUID) -> None:
    evidence: dict[str, list[str]] = defaultdict(list)
    confidence: dict[str, list[float]] = defaultdict(list)
    for fact in db.query(BusinessFactDraft).filter(BusinessFactDraft.tenant_id == tenant_id).all():
        try:
            key = canonical_taxonomy_key(fact.fact_type)
        except ValueError:
            continue
        evidence[key].append(_brief(fact.payload or {}))
        if fact.extraction_confidence is not None:
            confidence[key].append(float(fact.extraction_confidence))

    for chunk in db.query(DocumentChunk).filter(DocumentChunk.tenant_id == tenant_id).all():
        raw_key = chunk.detected_category or chunk.primary_category
        if not raw_key:
            continue
        try:
            key = canonical_taxonomy_key(raw_key)
        except ValueError:
            continue
        if not evidence[key]:
            evidence[key].append(chunk.content.strip().replace("\n", " ")[:180])

    existing = {
        row.category_key: row
        for row in db.query(CategorySummary).filter(CategorySummary.tenant_id == tenant_id).all()
    }
    for definition in CATEGORY_DEFINITIONS:
        row = existing.get(definition.key)
        if row is None:
            row = CategorySummary(
                tenant_id=tenant_id,
                category_key=definition.key,
                category_group=definition.group,
            )
            db.add(row)
        values = [value for value in evidence[definition.key] if value]
        row.category_group = definition.group
        row.item_count = len(values)
        row.status = "found" if values else "missing"
        row.summary = "; ".join(values[:3]) if values else None
        row.confidence = mean(confidence[definition.key]) if confidence[definition.key] else None
        row.needs_review = bool(values) and (
            not confidence[definition.key] or float(row.confidence or 0) < 0.75
        )
    db.commit()
