"""User repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.tenancy import User
from app.core.security import hash_password


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(db, User)

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_tenant(self, tenant_id: Any) -> list[User]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(User).filter(User.tenant_id == tid).all()

    def create_with_password(self, **kwargs) -> User:
        if "password" in kwargs:
            kwargs["hashed_password"] = hash_password(kwargs.pop("password"))
        user = User(**kwargs)
        return self.create(user)

    def verify_credentials(self, email: str, password: str) -> User | None:
        from app.core.security import verify_password
        user = self.get_by_email(email)
        if user and verify_password(password, user.hashed_password):
            return user
        return None
