"""Canonical category vocabulary and processing hints for knowledge ingestion.

The registry is deliberately data-only: routers validate against it while
workers use the same definitions to keep classification, chunks, facts and
projections aligned without embedding prompts in request handlers.
"""
from __future__ import annotations

from enum import Enum


class KnowledgeCategory(str, Enum):
    PRODUCTS = "products"
    SERVICES = "services"
    PRICING = "pricing"
    PLANS = "plans"
    POLICIES = "policies"
    FAQS = "faqs"
    COMPETITORS = "competitors"
    CUSTOMER_SEGMENTS = "customer_segments"
    SALES_PROCESSES = "sales_processes"
    SUPPORT_PROCESSES = "support_processes"
    PAYMENT_PROCESSES = "payment_processes"
    GENERAL = "general"


# Existing fact publishing uses singular names.  Keep that translation at the
# boundary rather than proliferating incompatible category strings internally.
_ALIASES = {
    "product": KnowledgeCategory.PRODUCTS.value, "service": KnowledgeCategory.SERVICES.value,
    "plan": KnowledgeCategory.PLANS.value, "policy": KnowledgeCategory.POLICIES.value,
    "faq": KnowledgeCategory.FAQS.value, "competitor": KnowledgeCategory.COMPETITORS.value,
    "customer_segment": KnowledgeCategory.CUSTOMER_SEGMENTS.value,
    "sales_process": KnowledgeCategory.SALES_PROCESSES.value,
    "support_process": KnowledgeCategory.SUPPORT_PROCESSES.value,
    "payment_process": KnowledgeCategory.PAYMENT_PROCESSES.value,
    "catalog": KnowledgeCategory.PRODUCTS.value, "sop": KnowledgeCategory.SALES_PROCESSES.value,
}

CATEGORY_CONFIGS = {
    category.value: {
        "entity_type": category.value.rstrip("s"),
        "chunking_hint": "faq_pair" if category is KnowledgeCategory.FAQS else "rule_with_exceptions" if category is KnowledgeCategory.POLICIES else "ordered_steps" if category.value.endswith("processes") else "layout",
        "instruction": f"Preserve useful tenant-specific {category.value} fields and source provenance.",
    }
    for category in KnowledgeCategory
}


def normalize_category(value: str | None, *, default: str = KnowledgeCategory.GENERAL.value) -> str:
    if not value:
        return default
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _ALIASES.get(normalized, normalized)
    if normalized not in CATEGORY_CONFIGS:
        raise ValueError(f"Unsupported knowledge category: {value}")
    return normalized


def fact_type_for_category(category: str) -> str:
    return {
        "products": "product", "services": "service", "plans": "plan", "policies": "policy",
        "faqs": "faq", "competitors": "competitor", "customer_segments": "customer_segment",
        "sales_processes": "sales_process", "support_processes": "support_process",
        "payment_processes": "payment_process",
    }.get(category, category if category.endswith("_process") else category.rstrip("s"))
