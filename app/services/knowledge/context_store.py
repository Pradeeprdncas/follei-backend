"""Tenant-safe FerretDB reasoning context access."""
from typing import Any
from app.config.ferretdb import get_context_database


def get_context(*, tenant_id: str, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    row = get_context_database()["tenant_context"].find_one(
        {"tenant_id": str(tenant_id), "subject_type": subject_type, "subject_id": str(subject_id)},
        {"_id": 0},
    )
    return row
