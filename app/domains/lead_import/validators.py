"""Validation logic for extracted lead data.

Validates email, phone, website, country, and blank/duplicate rows.
Used after AI extraction and before presenting the preview.
"""

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.integrations.channel_connection import TenantChannelConnection
from app.models.tenancy import Tenant


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
_WEBSITE_RE = re.compile(
    r"^(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z]{2,})(/[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]*)?$"
)

MINIMUM_ACCEPTED_LEADS = 50
DEFAULT_LEAD_CONTACT_REQUIREMENT = 1
DEFAULT_ACCEPTED_CONTACT_METHODS = ("email",)


def lead_import_policy(
    *,
    minimum_contact_methods: int = DEFAULT_LEAD_CONTACT_REQUIREMENT,
    accepted_contact_methods: tuple[str, ...] | list[str] = DEFAULT_ACCEPTED_CONTACT_METHODS,
    active_channel_types: tuple[str, ...] | list[str] = ("email",),
) -> dict[str, Any]:
    """Build the public contract from a tenant's resolved active channels."""
    accepted = list(dict.fromkeys(accepted_contact_methods))
    return {
        "minimum_accepted_rows": MINIMUM_ACCEPTED_LEADS,
        "minimum_contact_methods": minimum_contact_methods,
        "lead_contact_requirement": minimum_contact_methods,
        "contactability_rule": "minimum_active_channel_matches",
        "accepted_contact_methods": accepted,
        "active_channel_types": list(dict.fromkeys(active_channel_types)),
        "required_contact_methods": [],
        "row_rejection_mode": "individual",
        "batch_policy": "partial_accept",
        "policy_scope": "tenant",
        "configuration_valid": minimum_contact_methods <= len(accepted),
    }


def resolve_lead_import_policy(db: Session, tenant_id: UUID | str) -> dict[str, Any]:
    """Resolve one tenant's contactability rule from PostgreSQL only."""
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    tenant = db.get(Tenant, tenant_uuid)
    if tenant is None:
        raise ValueError("Tenant not found while resolving lead contact policy")
    requirement = int(tenant.lead_contact_requirement or DEFAULT_LEAD_CONTACT_REQUIREMENT)
    active_channels = [
        str(value).strip().lower()
        for value, in db.query(TenantChannelConnection.channel).filter(
            TenantChannelConnection.tenant_id == tenant_uuid,
            TenantChannelConnection.status == "active",
            TenantChannelConnection.enabled.is_(True),
        ).distinct().all()
    ]
    accepted = ["email"]
    if set(active_channels) & {"phone", "voice", "sms"}:
        accepted.append("phone")
    if "whatsapp" in active_channels:
        accepted.append("whatsapp")
    return lead_import_policy(
        minimum_contact_methods=requirement,
        accepted_contact_methods=accepted,
        active_channel_types=["email", *active_channels],
    )


def is_valid_email(email: Any) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def is_valid_phone(phone: Any) -> bool:
    if not phone or not isinstance(phone, (str, int)):
        return False
    cleaned = str(phone).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return bool(_PHONE_RE.match(cleaned))


def is_valid_website(website: Any) -> bool:
    if not website or not isinstance(website, str):
        return False
    return bool(_WEBSITE_RE.match(website.strip()))


def is_valid_country(country: Any) -> bool:
    if not country or not isinstance(country, str):
        return False
    return len(country.strip()) >= 2


def is_blank_row(data: dict[str, Any]) -> bool:
    """Check if a row is entirely empty or whitespace."""
    return all(
        v is None or (isinstance(v, str) and not v.strip())
        for v in data.values()
    )


def validate_lead_row(extracted: dict[str, Any], *, policy: dict[str, Any] | None = None) -> list[str]:
    """Validate an extracted lead row and return a list of error messages."""
    errors: list[str] = []

    if is_blank_row(extracted):
        errors.append("Blank row")
        return errors

    email = extracted.get("email")
    phone = extracted.get("phone")
    whatsapp = extracted.get("whatsapp")
    resolved = policy or lead_import_policy()
    accepted_methods = list(resolved["accepted_contact_methods"])
    minimum_contact_methods = int(resolved["minimum_contact_methods"])
    method_is_valid = {
        "email": is_valid_email(email),
        "phone": is_valid_phone(phone),
        # A standard mobile/phone value is also a usable WhatsApp identity.
        "whatsapp": is_valid_phone(whatsapp) or is_valid_phone(phone),
    }
    valid_contact_methods = sum(bool(method_is_valid.get(method)) for method in accepted_methods)
    if valid_contact_methods < minimum_contact_methods:
        available = ", ".join(accepted_methods)
        errors.append(
            f"Tenant requires at least {minimum_contact_methods} valid active-channel contact method(s); provide: {available}"
        )

    if "email" in accepted_methods and email and not is_valid_email(email):
        errors.append(f"Invalid email: {email}")
    if ("phone" in accepted_methods or "whatsapp" in accepted_methods) and phone and not is_valid_phone(phone):
        errors.append(f"Invalid phone: {phone}")
    if "whatsapp" in accepted_methods and whatsapp and not is_valid_phone(whatsapp):
        errors.append(f"Invalid WhatsApp: {whatsapp}")
    website = extracted.get("website")
    if website and not is_valid_website(website):
        errors.append(f"Invalid website: {website}")
    country = extracted.get("country")
    if country and not is_valid_country(country):
        errors.append(f"Invalid country: {country}")

    return errors


def evaluate_lead_batch(rows: list[dict[str, Any]], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the partial-accept contract without mutating or dropping evidence."""
    resolved = policy or lead_import_policy()
    validation = [
        {"row_index": index, "row": row, "reasons": validate_lead_row(row, policy=resolved)}
        for index, row in enumerate(rows)
    ]
    accepted = [item for item in validation if not item["reasons"]]
    rejected = [item for item in validation if item["reasons"]]
    return {
        "accepted": accepted,
        "rejected": rejected,
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "can_proceed": len(accepted) >= MINIMUM_ACCEPTED_LEADS,
        "policy": resolved,
    }
