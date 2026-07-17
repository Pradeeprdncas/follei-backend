"""Users router — delegates to OrganizationService."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.services.organization_service import OrganizationService
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


def _org_service(db: Session = Depends(get_db)) -> OrganizationService:
    return OrganizationService(db)


@router.post("/", response_model=UserRead)
def create_user(payload: UserCreate, svc: OrganizationService = Depends(_org_service)):
    data = payload.model_dump()
    password = data.pop("password")
    return svc.create_user(password=password, **data)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, svc: OrganizationService = Depends(_org_service)):
    return svc.get_user(user_id)
