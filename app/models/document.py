"""Canonical Document compatibility export.

All new ingestion/RAG code must use the UUID business-document model.  This
module keeps the existing RAG import path stable while avoiding a second ORM
mapping for the same `documents` table.
"""
from app.models.tenancy import Tenant  # registers the canonical tenants mapping first
from app.models.knowledge.document import Document

__all__ = ["Document", "Tenant"]
