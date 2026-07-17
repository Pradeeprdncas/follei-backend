from typing import Any


def map_contact(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    external_id = payload.get("id") or payload.get("external_id")
    if not external_id:
        raise ValueError("Contact external id is required.")
    return {
        "provider": provider,
        "external_id": str(external_id),
        "first_name": payload.get("first_name") or payload.get("firstname"),
        "last_name": payload.get("last_name") or payload.get("lastname"),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "company": payload.get("company") or payload.get("account_name"),
    }


def map_lead(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    full_name = payload.get("full_name") or " ".join(
        part for part in [payload.get("first_name"), payload.get("last_name")] if part
    )
    lead_name = full_name or payload.get("name")
    if not lead_name:
        raise ValueError("Lead name is required.")
    return {
        "provider": provider,
        "external_id": payload.get("id") or payload.get("external_id"),
        "full_name": lead_name,
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "company": payload.get("company"),
        "status": payload.get("status"),
        "source": payload.get("source"),
    }
