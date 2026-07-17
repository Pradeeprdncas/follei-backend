"""Tenants domain — multi-tenant organization management."""
from app.models.tenancy import Tenant
from app.domains.tenants.events import *

__all__ = ["Tenant"]
