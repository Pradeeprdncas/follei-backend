"""Tenant domain events."""
from dataclasses import dataclass
from app.events.base import DomainEvent


def build_tenant_created_event(tenant_id: str, name: str, domain: str = None) -> dict:
    return {
        "tenant_id": tenant_id,
        "name": name,
        "domain": domain,
    }


def build_tenant_updated_event(tenant_id: str, changes: dict) -> dict:
    return {
        "tenant_id": tenant_id,
        "changes": changes,
    }
