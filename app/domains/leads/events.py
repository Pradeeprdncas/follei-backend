"""Lead domain events."""
from dataclasses import dataclass


def build_lead_created_event(lead_id: str, tenant_id: str, email: str) -> dict:
    return {"lead_id": lead_id, "tenant_id": tenant_id, "email": email}


def build_lead_temperature_changed_event(lead_id: str, tenant_id: str, previous: str, current: str, score: float) -> dict:
    return {
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "previous_temperature": previous,
        "current_temperature": current,
        "score": score,
    }


def build_lead_score_updated_event(lead_id: str, tenant_id: str, score: int, delta: int) -> dict:
    return {"lead_id": lead_id, "tenant_id": tenant_id, "score": score, "delta": delta}
