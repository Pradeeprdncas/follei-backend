"""Build the complete UI state from PostgreSQL control-plane records only."""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import CategorySummary, IngestionRun, OnboardingConfirmation
from app.models.onboarding_profile import OnboardingProfile
from app.services.knowledge.categories import CATEGORY_DEFINITIONS, MANDATORY_GROUPS


VALID_RESOLUTIONS = {"provided", "not_applicable", "confidential", "continue_without"}


def _category_rows(db: Session, tenant_id: uuid.UUID) -> list[dict[str, object]]:
    stored = {
        row.category_key: row
        for row in db.query(CategorySummary).filter(CategorySummary.tenant_id == tenant_id).all()
    }
    return [
        {
            "key": definition.key,
            "label": definition.label,
            "category_group": definition.group,
            "mandatory_group": definition.mandatory_group,
            "status": stored[definition.key].status if definition.key in stored else "missing",
            "count": stored[definition.key].item_count if definition.key in stored else 0,
            "summary": stored[definition.key].summary if definition.key in stored else None,
            "confidence": float(stored[definition.key].confidence) if definition.key in stored and stored[definition.key].confidence is not None else None,
            "needs_review": stored[definition.key].needs_review if definition.key in stored else False,
        }
        for definition in CATEGORY_DEFINITIONS
    ]


def build_onboarding_state(db: Session, tenant_id: uuid.UUID) -> dict[str, object]:
    profile = db.query(OnboardingProfile).filter(OnboardingProfile.tenant_id == tenant_id).first()
    sources = db.query(KnowledgeSource).filter(KnowledgeSource.tenant_id == tenant_id).order_by(KnowledgeSource.created_at).all()
    runs = db.query(IngestionRun).filter(IngestionRun.tenant_id == tenant_id).order_by(IngestionRun.created_at.desc()).all()
    categories = _category_rows(db, tenant_id)
    confirmations = db.query(OnboardingConfirmation).filter(OnboardingConfirmation.tenant_id == tenant_id).all()
    confirmation_map = {row.requirement_key: row for row in confirmations}

    found_by_mandatory_group: dict[str, list[str]] = defaultdict(list)
    for category in categories:
        if category["mandatory_group"] and category["status"] in {"found", "partial"} and int(category["count"]) > 0:
            found_by_mandatory_group[str(category["mandatory_group"])].append(str(category["key"]))

    missing_groups = [key for key in MANDATORY_GROUPS if not found_by_mandatory_group[key]]
    confirmations_needed = [key for key in missing_groups if key not in confirmation_map]
    important_missing = [
        {"requirement": key, "acceptable_categories": list(MANDATORY_GROUPS[key])}
        for key in missing_groups
    ]
    optional_missing = [
        category["key"] for category in categories
        if category["mandatory_group"] is None and category["status"] == "missing"
    ]

    profile_missing = []
    if not profile:
        profile_missing = ["company_name", "timezone", "industry"]
    else:
        profile_missing = [field for field in ("company_name", "timezone", "industry") if not getattr(profile, field, None)]

    can_continue = not profile_missing and not confirmations_needed
    unsafe_confirmations = {
        key for key, row in confirmation_map.items() if row.resolution == "continue_without"
    }
    ready_for_autonomous_actions = can_continue and not missing_groups and not unsafe_confirmations

    return {
        "step": "knowledge_review",
        "progress": {
            "profile_complete": not profile_missing,
            "sources_connected": len(sources),
            "runs_active": sum(run.status in {"queued", "running", "retrying"} for run in runs),
            "categories_found": sum(category["status"] == "found" for category in categories),
            "categories_total": len(categories),
        },
        "sources": [
            {
                "id": str(source.id), "name": source.name, "type": source.source_type,
                "status": source.status, "config": source.config,
            }
            for source in sources
        ],
        "runs": [
            {
                "id": str(run.id), "source_id": str(run.source_id), "status": run.status,
                "page_count": run.page_count, "document_count": run.document_count,
                "error": run.error,
            }
            for run in runs[:20]
        ],
        "category_summaries": categories,
        "missing_data": {"profile": profile_missing, "optional": optional_missing},
        "important_missing_data": important_missing,
        "confirmations_needed": confirmations_needed,
        "confirmations": [
            {
                "requirement": row.requirement_key, "resolution": row.resolution,
                "note": row.note, "confirmed_at": row.confirmed_at.isoformat(),
            }
            for row in confirmations
        ],
        "can_continue": can_continue,
        "ready_for_autonomous_actions": ready_for_autonomous_actions,
    }
