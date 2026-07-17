"""Tenants router — delegates to OrganizationService."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.services.organization_service import OrganizationService
from app.schemas.tenant import TenantCreate, TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _org_service(db: Session = Depends(get_db)) -> OrganizationService:
    return OrganizationService(db)


@router.post("/", response_model=TenantRead)
def create_tenant(payload: TenantCreate, svc: OrganizationService = Depends(_org_service)):
    return svc.create_tenant(**payload.model_dump())


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(tenant_id: UUID, svc: OrganizationService = Depends(_org_service)):
    return svc.get_tenant(tenant_id)


@router.get("/", response_model=list[TenantRead])
def list_tenants(svc: OrganizationService = Depends(_org_service)):
    return svc.list_tenants()


@router.delete("/{tenant_id}")
def delete_tenant(tenant_id: UUID, svc: OrganizationService = Depends(_org_service)):
    svc.delete_tenant(tenant_id)
    return {"ok": True}
