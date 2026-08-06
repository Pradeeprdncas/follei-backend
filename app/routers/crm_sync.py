"""Tenant-authenticated HubSpot connection and three-store synchronization API."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id
from app.models.crm import CRMRecord, CRMSyncRun, TenantCRMConnection
from app.services.crm.hubspot import HubSpotClient, HubSpotError
from app.services.crm.schemas import CRMConnectionResponse, CRMRecordResponse, HubSpotConnectionCreate, HubSpotSyncRequest
from app.services.crm.sync import encrypt_crm_token, sync_hubspot

router = APIRouter(prefix="/api/v1/crm", tags=["CRM Sync"])


def _connection_payload(row: TenantCRMConnection) -> CRMConnectionResponse:
    return CRMConnectionResponse(
        id=str(row.id), provider=row.provider, status=row.status,
        external_account_id=row.external_account_id, scopes=list(row.scopes or []),
        last_synced_at=row.last_synced_at.isoformat() if row.last_synced_at else None,
        last_error=row.last_error,
    )


@router.get("/connections", response_model=list[CRMConnectionResponse])
def list_connections(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    rows = db.query(TenantCRMConnection).filter_by(tenant_id=UUID(tenant_id)).order_by(TenantCRMConnection.created_at).all()
    return [_connection_payload(row) for row in rows]


@router.post("/hubspot/connections", response_model=CRMConnectionResponse, status_code=status.HTTP_201_CREATED)
async def connect_hubspot(body: HubSpotConnectionCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    token = body.access_token.get_secret_value()
    if body.validate_connection:
        client = HubSpotClient(token)
        try:
            await client.validate()
        except HubSpotError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        finally:
            await client.close()
    tenant_uuid = UUID(tenant_id)
    connection = db.query(TenantCRMConnection).filter_by(tenant_id=tenant_uuid, provider="hubspot").first()
    if connection:
        connection.encrypted_access_token = encrypt_crm_token(token)
        connection.status = "active"
        connection.last_error = None
    else:
        connection = TenantCRMConnection(tenant_id=tenant_uuid, provider="hubspot", status="active", encrypted_access_token=encrypt_crm_token(token), scopes=[], sync_cursor={})
        db.add(connection)
    db.commit()
    db.refresh(connection)
    return _connection_payload(connection)


@router.delete("/hubspot/connections", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_hubspot(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    connection = db.query(TenantCRMConnection).filter_by(tenant_id=UUID(tenant_id), provider="hubspot").first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HubSpot connection not found")
    connection.status = "disconnected"
    connection.encrypted_access_token = None
    db.commit()
    return None


@router.post("/hubspot/sync", status_code=status.HTTP_202_ACCEPTED)
async def run_hubspot_sync(body: HubSpotSyncRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    tenant_uuid = UUID(tenant_id)
    connection = db.query(TenantCRMConnection).filter_by(tenant_id=tenant_uuid, provider="hubspot", status="active").first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connect HubSpot for this tenant before syncing")
    try:
        run = await sync_hubspot(db, tenant_id=tenant_uuid, connection=connection, resources=list(body.resources), page_size=body.page_size, max_pages_per_resource=body.max_pages_per_resource, project_now=body.project_now)
    except HubSpotError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"id": str(run.id), "provider": run.provider, "status": run.status, "object_counts": run.object_counts, "projection_event_count": len(run.event_ids or []), "error": run.error}


@router.get("/records", response_model=list[CRMRecordResponse])
def list_records(object_type: str | None = Query(default=None, pattern="^(contact|company|deal)$"), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    query = db.query(CRMRecord).filter_by(tenant_id=UUID(tenant_id), provider="hubspot")
    if object_type:
        query = query.filter(CRMRecord.object_type == object_type)
    rows = query.order_by(CRMRecord.synced_at.desc()).limit(limit).all()
    return [CRMRecordResponse(id=str(row.id), provider=row.provider, object_type=row.object_type, external_id=row.external_id, lead_id=str(row.lead_id) if row.lead_id else None, customer_id=str(row.customer_id) if row.customer_id else None, canonical_data=dict(row.canonical_data or {}), source_revision=row.source_revision, synced_at=row.synced_at.isoformat()) for row in rows]


@router.get("/sync-runs")
def list_sync_runs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    rows = db.query(CRMSyncRun).filter_by(tenant_id=UUID(tenant_id), provider="hubspot").order_by(CRMSyncRun.started_at.desc()).limit(limit).all()
    return [{"id": str(row.id), "status": row.status, "resources": row.requested_resources, "object_counts": row.object_counts, "projection_event_count": len(row.event_ids or []), "error": row.error, "started_at": row.started_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None} for row in rows]
