"""Platform router — delegates to PlatformService (admin CRUD)."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/database", tags=["Database CRUD"])


class RecordPayload(BaseModel):
    data: dict[str, Any] = Field(..., examples=[{"tenant_id": "00000000-0000-0000-0000-000000000000", "name": "Example"}])


def _svc(db: Session = Depends(get_db)) -> PlatformService:
    return PlatformService(db)


@router.get("/tables")
def list_tables(svc: PlatformService = Depends(_svc)):
    return svc.list_tables()


@router.get("/{table_name}/schema")
def get_table_schema(table_name: str, svc: PlatformService = Depends(_svc)):
    return svc.get_table_schema(table_name)


@router.get("/{table_name}/records")
def list_records(table_name: str, limit: int = Query(default=50, ge=1, le=500),
                 offset: int = Query(default=0, ge=0), svc: PlatformService = Depends(_svc)):
    return svc.list_records(table_name, limit, offset)


@router.post("/{table_name}/records", status_code=status.HTTP_201_CREATED)
def create_record(table_name: str, payload: RecordPayload, svc: PlatformService = Depends(_svc)):
    return svc.create_record(table_name, payload.data)


@router.get("/{table_name}/records/{record_id}")
def get_record(table_name: str, record_id: UUID, svc: PlatformService = Depends(_svc)):
    return svc.get_record(table_name, record_id)


@router.patch("/{table_name}/records/{record_id}")
def update_record(table_name: str, record_id: UUID, payload: RecordPayload,
                  svc: PlatformService = Depends(_svc)):
    return svc.update_record(table_name, record_id, payload.data)


@router.delete("/{table_name}/records/{record_id}")
def delete_record(table_name: str, record_id: UUID, svc: PlatformService = Depends(_svc)):
    return svc.delete_record(table_name, record_id)
