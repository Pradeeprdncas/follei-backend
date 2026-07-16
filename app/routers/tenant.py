from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4

from app.database import get_db
from app.models.tenancy import Tenant
from app.schemas.tenant import TenantCreate, TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/", response_model=TenantRead)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    if payload.domain:
        existing = db.query(Tenant).filter(
            Tenant.domain == payload.domain
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Tenant domain already exists"
            ) 

    tenant = Tenant(
        id=uuid4(),
        **payload.model_dump()
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return tenant


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db)
):
    tenant = db.get(Tenant, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    return tenant


@router.get("/", response_model=list[TenantRead])
def list_tenants(db: Session = Depends(get_db)):
    return db.query(Tenant).all()


@router.delete("/{tenant_id}")
def delete_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db)
):
    tenant = db.get(Tenant, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    db.delete(tenant)
    db.commit()

    return {
    }