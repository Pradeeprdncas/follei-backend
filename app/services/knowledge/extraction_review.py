"""Group extracted business facts into the onboarding review tabs."""
from sqlalchemy.orm import Session

from app.models.knowledge.fact_draft import BusinessFactDraft

# Every review tab is backed by an extraction schema and operational publisher,
# including Plans and Customer Segments.
FACT_TYPE_TO_CATEGORY = {
    "product": "Products",
    "service": "Services",
    "pricing": "Pricing",
    "plan": "Plans",
    "policy": "Policies",
    "sla": "SLAs",
    "faq": "FAQs",
    "competitor": "Competitors",
    "customer_segment": "Customer Segments",
    "sales_process": "Sales Processes",
    "support_process": "Support Processes",
    "payment_process": "Payment Processes",
}
ALL_CATEGORIES = tuple(dict.fromkeys(FACT_TYPE_TO_CATEGORY.values()))


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
