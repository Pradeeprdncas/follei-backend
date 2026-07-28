"""Evidence-led revenue signals without an under-trained conversion classifier."""
from __future__ import annotations

import re
from typing import Any

_MONEY = re.compile(
    r"(?P<currency>[$₹€£])\s*(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>k|m|million|lakh|crore)?",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*%")
_VALUE_TERMS = re.compile(
    r"\b(?:revenue|roi|return on investment|cost savings?|save|reduce costs?|"
    r"payback|margin|productivity|conversion|deal value|contract value)\b",
    re.IGNORECASE,
)
_URGENCY_TERMS = re.compile(
    r"\b(?:asap|urgent|immediately|this (?:week|month|quarter)|"
    r"within \d+ (?:days?|weeks?|months?))\b",
    re.IGNORECASE,
)


class RevenueIntelligenceService:
    @classmethod
    def analyze(
        cls,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        crm_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        crm_context = crm_context or {}
        money = [match.group(0) for match in _MONEY.finditer(text)]
        percentages = _PERCENT.findall(text)
        value_terms = sorted({match.group(0).lower() for match in _VALUE_TERMS.finditer(text)})
        urgency = [match.group(0) for match in _URGENCY_TERMS.finditer(text)]

        structured_value = next(
            (
                value
                for value in (
                    crm_context.get("deal_value"),
                    crm_context.get("annual_contract_value"),
                    metadata.get("deal_value"),
                    metadata.get("annual_contract_value"),
                )
                if value not in (None, "")
            ),
            None,
        )
        evidence_points = (
            min(2, len(money)) * 18
            + min(2, len(percentages)) * 12
            + min(3, len(value_terms)) * 12
            + min(1, len(urgency)) * 10
            + (20 if structured_value is not None else 0)
        )
        return {
            "revenue_score": float(min(100, evidence_points)),
            "monetary_evidence": money,
            "percentage_evidence": percentages,
            "value_drivers": value_terms,
            "urgency_evidence": urgency,
            "structured_opportunity_value": structured_value,
            "source": "conversation_and_crm_evidence",
        }
