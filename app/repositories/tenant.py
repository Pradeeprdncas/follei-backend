"""Tenant repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.tenancy import Tenant


class TenantRepository(BaseRepository[Tenant]):
    def __init__(self, db: Session):
        super().__init__(db, Tenant)

    def get_by_domain(self, domain: str) -> Tenant | None:
        return self.db.query(Tenant).filter(Tenant.domain == domain).first()

    def get_by_slug(self, slug: str) -> Tenant | None:
        return self.db.query(Tenant).filter(Tenant.slug == slug).first()

    def get_active(self) -> list[Tenant]:
        return self.db.query(Tenant).filter(Tenant.is_active == True).all()
