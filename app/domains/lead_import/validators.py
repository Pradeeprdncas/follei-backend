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


def validate_lead_row(extracted: dict[str, Any]) -> list[str]:
    """Validate an extracted lead row and return a list of error messages."""
    errors: list[str] = []

    if is_blank_row(extracted):
        errors.append("Blank row")
        return errors

    email = extracted.get("email")
    phone = extracted.get("phone")
    if not email and not phone:
        errors.append("At least one of email or phone is required")

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
