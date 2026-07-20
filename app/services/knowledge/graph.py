"""Tenant-scoped business knowledge graph construction and bounded traversal."""
from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models.knowledge.entity import Entity, EntityRelation
from app.models.knowledge.fact_draft import BusinessFactDraft

_ENTITY_TYPE_BY_FACT = {
    "product": "product",
    "service": "service",
    "pricing": "pricing_plan",
    "policy": "policy",
    "faq": "faq",
    "competitor": "competitor",
    "customer_segment": "customer_segment",
    "sales_process": "sales_process",
    "support_process": "support_process",
    "payment_process": "payment_process",
}
_NAME_FIELDS = ("name", "title", "question")
_RELATION_FIELDS = (
    ("features", "feature", "has_feature"),
    ("benefits", "benefit", "delivers_benefit"),
    ("customer_segments", "customer_segment", "targets"),
    ("competitors", "competitor", "competes_with"),
    ("requirements", "requirement", "supports_requirement"),
    ("integrations", "integration", "supports_integration"),
    ("objections", "objection", "addresses_objection"),
)


def _name(payload: dict[str, Any], fallback: str) -> str:
    for field in _NAME_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _values(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field, [])
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def ensure_entity(db: Session, *, tenant_id: Any, entity_type: str, name: str, metadata: dict[str, Any] | None = None) -> Entity:
    """Return one canonical entity per tenant/type/name, never crossing tenants."""
    entity = db.query(Entity).filter(
        Entity.tenant_id == tenant_id,
        Entity.entity_type == entity_type,
        func.lower(Entity.name) == name.lower(),
    ).first()
    if entity:
        if metadata:
            entity.metadata_ = {**(entity.metadata_ or {}), **metadata}
        return entity
    entity = Entity(tenant_id=tenant_id, entity_type=entity_type, name=name, metadata_=metadata or {})
    db.add(entity)
    db.flush()
    return entity


def ensure_relation(db: Session, *, tenant_id: Any, source: Entity, target: Entity, relation_type: str, metadata: dict[str, Any] | None = None) -> EntityRelation:
    relation = db.query(EntityRelation).filter(
        EntityRelation.tenant_id == tenant_id,
        EntityRelation.source_entity_id == source.id,
        EntityRelation.target_entity_id == target.id,
        EntityRelation.relation_type == relation_type,
    ).first()
    if relation:
        if metadata:
            relation.metadata_ = {**(relation.metadata_ or {}), **metadata}
        return relation
    relation = EntityRelation(
        tenant_id=tenant_id,
        source_entity_id=source.id,
        target_entity_id=target.id,
        relation_type=relation_type,
        confidence=1.0,
        metadata_=metadata or {},
    )
    db.add(relation)
    db.flush()
    return relation


def sync_approved_fact_to_graph(db: Session, *, draft: BusinessFactDraft) -> list[EntityRelation]:
    """Create cited graph nodes/relations only after the source fact is approved."""
    if draft.approval_status != "approved":
        raise ValueError("Only approved facts may create graph knowledge")
    payload = draft.payload or {}
    entity_type = _ENTITY_TYPE_BY_FACT.get(draft.fact_type, "business_fact")
    citation = draft.citation or {}
    provenance = {"fact_draft_id": str(draft.id), "citation": citation}
    primary = ensure_entity(
        db,
        tenant_id=draft.tenant_id,
        entity_type=entity_type,
        name=_name(payload, draft.fact_type.replace("_", " ")),
        metadata=provenance,
    )
    document_name = citation.get("document_name")
    relations: list[EntityRelation] = []
    if isinstance(document_name, str) and document_name.strip():
        document = ensure_entity(
            db,
            tenant_id=draft.tenant_id,
            entity_type="document",
            name=document_name.strip(),
            metadata={"document_id": citation.get("document_id"), "source_uri": citation.get("source_uri")},
        )
        relations.append(ensure_relation(db, tenant_id=draft.tenant_id, source=document, target=primary, relation_type="defines", metadata=provenance))

    for field, target_type, relation_type in _RELATION_FIELDS:
        for value in _values(payload, field):
            target = ensure_entity(db, tenant_id=draft.tenant_id, entity_type=target_type, name=value, metadata=provenance)
            relations.append(ensure_relation(db, tenant_id=draft.tenant_id, source=primary, target=target, relation_type=relation_type, metadata=provenance))
    for relationship in payload.get("relationships", []) if isinstance(payload.get("relationships"), list) else []:
        if not isinstance(relationship, dict):
            continue
        target_name = relationship.get("target")
        if not isinstance(target_name, str) or not target_name.strip():
            continue
        source_name = relationship.get("source")
        if isinstance(source_name, str) and source_name.strip():
            source = ensure_entity(
                db,
                tenant_id=draft.tenant_id,
                entity_type=str(relationship.get("source_type") or "business_concept"),
                name=source_name.strip(),
                metadata=provenance,
            )
        else:
            source = primary
        target = ensure_entity(
            db,
            tenant_id=draft.tenant_id,
            entity_type=str(relationship.get("target_type") or "business_concept"),
            name=target_name.strip(),
            metadata=provenance,
        )
        relation_type = str(relationship.get("relation") or "related_to").strip().lower().replace(" ", "_")
        relations.append(ensure_relation(db, tenant_id=draft.tenant_id, source=source, target=target, relation_type=relation_type, metadata=provenance))
    return relations


def supersede_fact_in_graph(db: Session, *, draft: BusinessFactDraft, winner_fact_id: str) -> int:
    """Mark graph relations derived from a losing fact as non-retrievable."""
    changed = 0
    relations = db.query(EntityRelation).filter(EntityRelation.tenant_id == draft.tenant_id).all()
    for relation in relations:
        metadata = dict(relation.metadata_ or {})
        if str(metadata.get("fact_draft_id") or "") != str(draft.id):
            continue
        relation.metadata_ = {**metadata, "superseded_by": str(winner_fact_id)}
        changed += 1
    return changed


def traverse_graph(db: Session, *, tenant_id: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Return at most one-hop, cited relations matching a tenant-local query."""
    terms = [term for term in re.findall(r"[\w-]{3,}", query.lower()) if term not in {"what", "with", "that", "this", "about", "does", "have", "from", "according", "each", "contain", "contains", "into"}][:8]
    if not terms:
        return []
    try:
        predicates = [Entity.name.ilike(f"%{term}%") for term in terms]
        seeds = db.query(Entity).filter(Entity.tenant_id == tenant_id, or_(*predicates)).limit(5).all()
        if not seeds:
            return []
        seed_ids = [entity.id for entity in seeds]
        relations = db.query(EntityRelation).filter(
            EntityRelation.tenant_id == tenant_id,
            or_(EntityRelation.source_entity_id.in_(seed_ids), EntityRelation.target_entity_id.in_(seed_ids)),
        ).limit(max(1, min(limit, 30))).all()
        entity_ids = {entity.id for entity in seeds}
        for relation in relations:
            entity_ids.update((relation.source_entity_id, relation.target_entity_id))
        entities = {entity.id: entity for entity in db.query(Entity).filter(Entity.tenant_id == tenant_id, Entity.id.in_(entity_ids)).all()}
        result = [
            {
                "from": entities[relation.source_entity_id].name,
                "from_entity_id": str(relation.source_entity_id),
                "relation": relation.relation_type,
                "to": entities[relation.target_entity_id].name,
                "to_entity_id": str(relation.target_entity_id),
                "citation": (relation.metadata_ or {}).get("citation"),
                "confidence": float(relation.confidence) if relation.confidence is not None else None,
            }
            for relation in relations
            if relation.source_entity_id in entities
            and relation.target_entity_id in entities
            and not (relation.metadata_ or {}).get("superseded_by")
        ]
        required = 1 if len(set(terms)) <= 2 else 2
        return [
            item for item in result
            if sum(
                1 for term in set(terms)
                if term in f"{item['from']} {item['relation']} {item['to']}".lower()
            ) >= required
        ]
    except Exception:
        # A graph is an enrichment layer; it must never block a tenant response.
        return []


