"""Base repository with common CRUD operations."""
from typing import Any, Generic, TypeVar
from uuid import UUID
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic base repository providing standard CRUD operations."""

    def __init__(self, db: Session, model_class: type[T]):
        self.db = db
        self.model_class = model_class

    def _to_uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    def create(self, instance: T) -> T:
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def get_by_id(self, id_: Any) -> T | None:
        pk = self._to_uuid(id_)
        return self.db.get(self.model_class, pk)

    def get_by_ids(self, ids: list[Any]) -> list[T]:
        uuids = [self._to_uuid(i) for i in ids]
        return self.db.query(self.model_class).filter(
            self.model_class.id.in_(uuids)
        ).all()

    def get_by_tenant(self, tenant_id: Any) -> list[T]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(self.model_class).filter(
            self.model_class.tenant_id == tid
        ).all()

    def list_all(self) -> list[T]:
        return self.db.query(self.model_class).all()

    def update(self, id_: Any, **kwargs) -> T | None:
        pk = self._to_uuid(id_)
        instance = self.db.get(self.model_class, pk)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            self.db.commit()
            self.db.refresh(instance)
        return instance

    def delete(self, id_: Any) -> bool:
        pk = self._to_uuid(id_)
        instance = self.db.get(self.model_class, pk)
        if instance:
            self.db.delete(instance)
            self.db.commit()
            return True
        return False
