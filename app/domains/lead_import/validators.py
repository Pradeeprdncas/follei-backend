"""Validation logic for extracted lead data.

Validates email, phone, website, country, and blank/duplicate rows.
Used after AI extraction and before presenting the preview.
"""

import re
from typing import Any


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
_WEBSITE_RE = re.compile(
    r"^(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z]{2,})(/[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]*)?$"
)

MINIMUM_ACCEPTED_LEADS = 50
MINIMUM_CONTACT_METHODS = 2


def lead_import_policy() -> dict[str, Any]:
    """Public contract: reject bad rows, continue only with 50 accepted rows."""
    return {
        "minimum_accepted_rows": MINIMUM_ACCEPTED_LEADS,
        "minimum_contact_methods": MINIMUM_CONTACT_METHODS,
        "required_contact_methods": ["email", "phone"],
        "row_rejection_mode": "individual",
        "batch_policy": "partial_accept",
    }


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


def validate_lead_row(extracted: dict[str, Any], *, minimum_contact_methods: int = MINIMUM_CONTACT_METHODS) -> list[str]:
    """Validate an extracted lead row and return a list of error messages."""
    errors: list[str] = []

    if is_blank_row(extracted):
        errors.append("Blank row")
        return errors

    email = extracted.get("email")
    phone = extracted.get("phone")
    contact_methods = sum(bool(value and str(value).strip()) for value in (email, phone))
    if contact_methods < minimum_contact_methods:
        errors.append(
            f"At least {minimum_contact_methods} contact methods are required; provide both email and phone"
        )

    if email and not is_valid_email(email):
        errors.append(f"Invalid email: {email}")
    if phone and not is_valid_phone(phone):
        errors.append(f"Invalid phone: {phone}")
    website = extracted.get("website")
    if website and not is_valid_website(website):
        errors.append(f"Invalid website: {website}")
    country = extracted.get("country")
    if country and not is_valid_country(country):
        errors.append(f"Invalid country: {country}")

    return errors


def evaluate_lead_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the partial-accept contract without mutating or dropping evidence."""
    validation = [
        {"row_index": index, "row": row, "reasons": validate_lead_row(row)}
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
        "policy": lead_import_policy(),
    }
