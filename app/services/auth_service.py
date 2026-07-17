"""Auth service — manages registration, login, token verification."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.tenant import TenantRepository
from app.repositories.user import UserRepository
from app.core.security import create_access_token, decode_access_token


class AuthService:
    def __init__(self, db: Session):
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)

    def register_tenant(self, name: str, domain: str | None,
                        admin_email: str, admin_password: str,
                        admin_first_name: str, admin_last_name: str,
                        business_phone_number: str | None = None,
                        business_email: str | None = None,
                        timezone: str = "Asia/Kolkata",
                        business_hours: dict[str, Any] | None = None,
                        forwarding_number: str | None = None,
                        auto_reply_enabled: bool = False,
                        channel_config: dict[str, Any] | None = None) -> dict:
        existing_tenant = self.tenant_repo.get_by_domain(domain) if domain else None
        if existing_tenant:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant domain already exists")

        existing_user = self.user_repo.get_by_email(admin_email)
        if existing_user:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists")

        from app.models.tenancy import Tenant
        tenant = Tenant(
            name=name, domain=domain,
            business_phone_number=business_phone_number,
            business_email=business_email,
            timezone=timezone,
            business_hours=business_hours,
            forwarding_number=forwarding_number,
            auto_reply_enabled=auto_reply_enabled,
            channel_config=channel_config,
        )
        tenant = self.tenant_repo.create(tenant)

        from app.models.tenancy import User
        user = User(
            tenant_id=tenant.id,
            email=admin_email,
            first_name=admin_first_name,
            last_name=admin_last_name,
            role="admin",
        )
        user = self.user_repo.create_with_password(email=admin_email, password=admin_password,
                                                    first_name=admin_first_name, last_name=admin_last_name,
                                                    role="admin", tenant_id=tenant.id)

        token = create_access_token(user.id, user.tenant_id)
        return {"access_token": token, "token_type": "bearer"}

    def login(self, email: str, password: str) -> dict:
        from fastapi import HTTPException, status
        user = self.user_repo.verify_credentials(email, password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
        token = create_access_token(user.id, user.tenant_id)
        return {"access_token": token, "token_type": "bearer"}

    def get_current_user(self, token: str):
        from fastapi import HTTPException, status
        try:
            payload = decode_access_token(token)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = self.user_repo.get_by_id(UUID(payload["sub"]))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
        return user
