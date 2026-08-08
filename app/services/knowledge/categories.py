"""One canonical taxonomy shared by ingestion, readiness and the frontend API."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnowledgeCategory(str, Enum):
    PRODUCTS = "products"
    SERVICES = "services"
    PRICING_PACKAGES = "pricing_packages"
    PLANS_SUBSCRIPTIONS = "plans_subscriptions"
    POLICIES_TERMS = "policies_terms"
    FAQS = "faqs"
    SALES_PROCESS = "sales_processes"
    LEAD_QUALIFICATION = "lead_qualification"
    SALES_MESSAGING = "sales_messaging"
    VALUE_PROPOSITIONS = "value_propositions"
    COMMON_OBJECTIONS = "common_objections"
    CUSTOMER_PAIN_POINTS = "customer_pain_points"
    BUYER_PERSONAS = "buyer_personas"
    CUSTOMER_SEGMENTS = "customer_segments"
    TARGET_INDUSTRIES = "target_industries"
    USE_CASES = "use_cases"
    CONTACT_COMPANY_INFORMATION = "contact_company_information"
    COMMUNICATION_PREFERENCES = "communication_preferences"
    SUPPORT_PROCESS = "support_processes"
    PAYMENT_BILLING_PROCESS = "payment_processes"
    EXISTING_DEALS_OPPORTUNITIES = "existing_deals_opportunities"
    FOLLOW_UP_PATTERNS = "follow_up_patterns"
    COMPETITORS = "competitors"
    DIFFERENTIATORS = "differentiators"
    POSITIONING_ANGLES = "positioning_angles"
    GENERAL = "general"

    # Source-compatible names retained for callers importing the old enum.
    PRICING = "pricing_packages"
    PLANS = "plans_subscriptions"
    POLICIES = "policies_terms"
    SALES_PROCESSES = "sales_processes"
    SUPPORT_PROCESSES = "support_processes"
    PAYMENT_PROCESSES = "payment_processes"


@dataclass(frozen=True)
class CategoryDefinition:
    key: str
    group: str
    label: str
    mandatory_group: str | None = None


_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "business": (
        ("products", "Products"), ("services", "Services"),
        ("pricing_packages", "Pricing & Packages"),
        ("plans_subscriptions", "Plans & Subscriptions"),
        ("policies_terms", "Policies & Terms"), ("faqs", "FAQs"),
    ),
    "sales": (
        ("sales_process", "Sales Process"), ("lead_qualification", "Lead Qualification"),
        ("sales_messaging", "Sales Messaging"), ("value_propositions", "Value Propositions"),
        ("common_objections", "Common Objections"), ("customer_pain_points", "Customer Pain Points"),
        ("buyer_personas", "Buyer Personas"),
    ),
    "customers": (
        ("customer_segments", "Customer Segments"), ("target_industries", "Target Industries"),
        ("use_cases", "Use Cases"), ("contact_company_information", "Contact & Company Information"),
        ("communication_preferences", "Communication Preferences"),
    ),
    "operations": (
        ("support_process", "Support Process"), ("payment_billing_process", "Payment & Billing Process"),
        ("existing_deals_opportunities", "Existing Deals & Opportunities"),
        ("follow_up_patterns", "Follow-up Patterns"),
    ),
    "competitive_intelligence": (
        ("competitors", "Competitors"), ("differentiators", "Differentiators"),
        ("positioning_angles", "Positioning Angles"),
    ),
}

MANDATORY_GROUPS: dict[str, tuple[str, ...]] = {
    "business_fundamentals": ("products", "services", "pricing_packages", "plans_subscriptions"),
    "customer_definition": ("customer_segments", "buyer_personas", "target_industries", "use_cases"),
    "value_positioning": ("value_propositions", "differentiators", "positioning_angles"),
    "process": ("sales_process", "support_process", "payment_billing_process"),
    "governance": ("policies_terms",),
}

_MANDATORY_BY_CATEGORY = {
    category: group for group, categories in MANDATORY_GROUPS.items() for category in categories
}

CATEGORY_DEFINITIONS: tuple[CategoryDefinition, ...] = tuple(
    CategoryDefinition(key, group, label, _MANDATORY_BY_CATEGORY.get(key))
    for group, values in _GROUPS.items() for key, label in values
)

_ALIASES = {
    # Legacy ingestion outputs stay stable so existing index/fact publishers do
    # not need a flag-day migration. canonical_taxonomy_key projects them into
    # the 25-category UI vocabulary.
    "product": "products", "service": "services", "pricing": "pricing",
    "plan": "plans", "policy": "policies", "faq": "faqs", "competitor": "competitors",
    "customer_segment": "customer_segments", "sales_process": "sales_processes",
    "support_process": "support_processes", "payment_process": "payment_processes",
    "catalog": "products", "sop": "sales_processes",
    "positioning": "positioning_angles", "contact_information": "contact_company_information",
}

CATEGORY_CONFIGS = {
    item.key: {
        "group": item.group,
        "label": item.label,
        "mandatory_group": item.mandatory_group,
        "entity_type": item.key.rstrip("s"),
        "chunking_hint": (
            "faq_pair" if item.key == "faqs" else
            "rule_with_exceptions" if item.key == "policies_terms" else
            "ordered_steps" if item.key.endswith("process") else "layout"
        ),
        "instruction": f"Preserve tenant-specific {item.label.lower()} and source provenance.",
    }
    for item in CATEGORY_DEFINITIONS
}
CATEGORY_CONFIGS["general"] = {
    "group": "uncategorized", "label": "General", "mandatory_group": None,
    "entity_type": "general", "chunking_hint": "layout",
    "instruction": "Preserve useful tenant-specific context and source provenance.",
}
for legacy, canonical in {
    "pricing": "pricing_packages", "plans": "plans_subscriptions", "policies": "policies_terms",
    "sales_processes": "sales_process", "support_processes": "support_process",
    "payment_processes": "payment_billing_process",
}.items():
    CATEGORY_CONFIGS[legacy] = {**CATEGORY_CONFIGS[canonical], "taxonomy_key": canonical}


def normalize_category(value: str | None, *, default: str = KnowledgeCategory.GENERAL.value) -> str:
    if not value:
        return default
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _ALIASES.get(normalized, normalized)
    if normalized not in CATEGORY_CONFIGS:
        raise ValueError(f"Unsupported knowledge category: {value}")
    return normalized


def fact_type_for_category(category: str) -> str:
    normalized = normalize_category(category)
    return {
        "products": "product", "services": "service", "plans_subscriptions": "plan", "plans": "plan",
        "policies_terms": "policy", "policies": "policy", "faqs": "faq", "competitors": "competitor",
        "customer_segments": "customer_segment", "sales_process": "sales_process", "sales_processes": "sales_process",
        "support_process": "support_process", "support_processes": "support_process",
        "payment_billing_process": "payment_process", "payment_processes": "payment_process",
    }.get(normalized, normalized.rstrip("s"))


def canonical_taxonomy_key(value: str | None) -> str:
    normalized = normalize_category(value)
    return {
        "pricing": "pricing_packages", "plans": "plans_subscriptions", "policies": "policies_terms",
        "sales_processes": "sales_process", "support_processes": "support_process",
        "payment_processes": "payment_billing_process",
    }.get(normalized, normalized)


def taxonomy_payload() -> list[dict[str, object]]:
    """Stable, display-ready taxonomy contract for clients."""
    return [
        {
            "key": item.key, "label": item.label, "group": item.group,
            "mandatory": item.mandatory_group is not None,
            "mandatory_group": item.mandatory_group,
        }
        for item in CATEGORY_DEFINITIONS
    ]
