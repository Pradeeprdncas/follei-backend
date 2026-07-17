"""Customer repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.customers.customer import Customer


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, db: Session):
        super().__init__(db, Customer)

    def get_by_tenant(self, tenant_id: Any) -> list[Customer]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Customer).filter(
            Customer.tenant_id == tid
        ).all()

    def get_by_email(self, tenant_id: Any, email: str) -> Customer | None:
        tid = self._to_uuid(tenant_id)
        return self.db.query(Customer).filter(
            Customer.tenant_id == tid,
            Customer.email == email,
        ).first()
