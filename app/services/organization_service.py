"""Organization service â€” manages tenants and users."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.tenant import TenantRepository
from app.repositories.user import UserRepository


class OrganizationService:
    def __init__(self, db: Session):
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)

    def list_tenants(self) -> list[Any]:
        return self.tenant_repo.list_all()

    def get_tenant(self, tenant_id: UUID) -> Any:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant

    def create_tenant(self, name: str, domain: str | None = None,
                      website: str | None = None, country_region: str | None = None,
                      industry: str | None = None, selected_channels: list[str] | None = None,
                      onboarding_profile: dict[str, Any] | None = None,
                      business_phone_number: str | None = None,
                      business_email: str | None = None,
                      timezone: str = "Asia/Kolkata",
                      business_hours: dict[str, Any] | None = None,
                      forwarding_number: str | None = None,
                      auto_reply_enabled: bool = False,
                      channel_config: dict[str, Any] | None = None) -> Any:
        from app.models.tenancy import Tenant
        tenant = Tenant(
            name=name, domain=domain, website=website, country_region=country_region,
            industry=industry, selected_channels=selected_channels, onboarding_profile=onboarding_profile,
            business_phone_number=business_phone_number,
            business_email=business_email,
            timezone=timezone,
            business_hours=business_hours,
            forwarding_number=forwarding_number,
            auto_reply_enabled=auto_reply_enabled,
            channel_config=channel_config,
        )
        return self.tenant_repo.create(tenant)

    def update_tenant(self, tenant_id: UUID, **kwargs) -> Any:
        tenant = self.tenant_repo.update(tenant_id, **kwargs)
        if not tenant:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant

    def delete_tenant(self, tenant_id: UUID) -> None:
        if not self.tenant_repo.delete(tenant_id):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Tenant not found")

    def list_users(self, tenant_id: UUID | None = None) -> list[Any]:
        if tenant_id:
            return self.user_repo.get_by_tenant(tenant_id)
        return self.user_repo.list_all()

    def get_user(self, user_id: UUID) -> Any:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def create_user(self, tenant_id: UUID, email: str, password: str,
                    first_name: str, last_name: str, role: str = "member") -> Any:
        return self.user_repo.create_with_password(
            tenant_id=tenant_id, email=email, password=password,
            first_name=first_name, last_name=last_name, role=role,
        )

    def update_user(self, user_id: UUID, **kwargs) -> Any:
        user = self.user_repo.update(user_id, **kwargs)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def delete_user(self, user_id: UUID) -> None:
        if not self.user_repo.delete(user_id):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="User not found")


