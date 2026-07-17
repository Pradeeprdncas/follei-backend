"""User domain events."""
from dataclasses import dataclass


def build_user_created_event(user_id: str, tenant_id: str, email: str, role: str) -> dict:
    return {"user_id": user_id, "tenant_id": tenant_id, "email": email, "role": role}
