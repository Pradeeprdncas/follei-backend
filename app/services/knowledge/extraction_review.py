"""Read/grouping layer over the existing business_fact_drafts table for the
onboarding extraction-review tabs. Does not rebuild fact extraction.
"""
from sqlalchemy.orm import Session

from app.models.knowledge.fact_draft import BusinessFactDraft

# "Plans" has no dedicated extraction fact_type yet (see FACT_TYPES in
# app/services/knowledge/fact_extraction.py) — it always renders as an empty
# category today. Included anyway so the UI's fixed set of tabs stays stable.
FACT_TYPE_TO_CATEGORY = {
    "product": "Products",
    "service": "Services",
    "pricing": "Pricing",
    "policy": "Policies",
    "faq": "FAQs",
    "competitor": "Competitors",
    "customer_segment": "Customer Segments",
    "sales_process": "Sales Processes",
    "support_process": "Support Processes",
    "payment_process": "Payment Processes",
}
ALL_CATEGORIES = (*dict.fromkeys(FACT_TYPE_TO_CATEGORY.values()), "Plans")


def _draft_to_item(draft: BusinessFactDraft) -> dict:
    return {
        "id": str(draft.id),
        "fact_type": draft.fact_type,
        "payload": draft.payload,
        "citation": draft.citation,
        "extraction_confidence": float(draft.extraction_confidence) if draft.extraction_confidence is not None else None,
        "approval_status": draft.approval_status,
        "created_at": draft.created_at,
    }


def group_extractions_by_category(db: Session, tenant_id, *, status: str = "draft") -> dict[str, list[dict]]:
    drafts = (
        db.query(BusinessFactDraft)
        .filter(BusinessFactDraft.tenant_id == tenant_id, BusinessFactDraft.approval_status == status)
        .order_by(BusinessFactDraft.created_at.desc())
        .all()
    )
    grouped: dict[str, list[dict]] = {category: [] for category in ALL_CATEGORIES}
    for draft in drafts:
        category = FACT_TYPE_TO_CATEGORY.get(draft.fact_type)
        if category:
            grouped[category].append(_draft_to_item(draft))
    return grouped
