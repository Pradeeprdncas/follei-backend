"""Tenant-authenticated HubSpot connection and three-store synchronization API."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.models.crm import CRMRecord, CRMSyncRun, TenantCRMConnection
from app.services.crm.hubspot import HubSpotClient, HubSpotError
from app.services.crm.schemas import CRMConnectionResponse, CRMRecordResponse, HubSpotConnectionCreate, HubSpotSyncRequest
from app.services.crm.sync import encrypt_crm_token, sync_hubspot
from app.services.integrations.hubspot_oauth import HubSpotOAuthError, HubSpotOAuthService
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.schemas.api_envelope import api_envelope

router = APIRouter(prefix="/api/v1/crm", tags=["CRM Sync"])
_settings = get_settings()


def _queue_hubspot_sync(db: Session, connection: TenantCRMConnection, resources: list[str], *, page_size: int = 100, max_pages: int = 10, project_now: bool = False):
    source = db.query(KnowledgeSource).filter_by(tenant_id=connection.tenant_id, source_type="hubspot").first()
    if source is None:
        source = KnowledgeSource(id=uuid4(), tenant_id=connection.tenant_id, name="HubSpot CRM", source_type="hubspot", status="queued", config={"connection_id": str(connection.id)})
        db.add(source)
    source.status = "queued"
    ingestion_run = IngestionRun(id=uuid4(), tenant_id=connection.tenant_id, source_id=source.id, status="queued")
    ingestion_job = SourceIngestionJob(id=uuid4(), tenant_id=connection.tenant_id, run_id=ingestion_run.id, job_type="hubspot_sync", target=connection.external_account_id, status="queued", payload={"resources": resources})
    crm_run = CRMSyncRun(id=uuid4(), tenant_id=connection.tenant_id, connection_id=connection.id, provider="hubspot", status="queued", requested_resources=resources, object_counts={}, event_ids=[])
    db.add_all([ingestion_run, ingestion_job, crm_run]); db.commit()
    ensure_topics(); producer = get_producer()
    producer.send(_settings.KAFKA_TOPIC_CRM_SYNC, key=str(crm_run.id), value={
        "crm_run_id": str(crm_run.id), "ingestion_run_id": str(ingestion_run.id), "ingestion_job_id": str(ingestion_job.id),
        "source_id": str(source.id), "connection_id": str(connection.id), "tenant_id": str(connection.tenant_id),
        "resources": resources, "page_size": page_size, "max_pages_per_resource": max_pages, "project_now": project_now,
    }); producer.flush()
    return crm_run, ingestion_run, ingestion_job


@router.post("/hubspot/oauth/start")
def start_hubspot_oauth(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id), user_id: str = Depends(get_authenticated_user_id)):
    try:
        url = HubSpotOAuthService().authorization_url(db, tenant_id=tenant_id, user_id=user_id)
    except HubSpotOAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return api_envelope({"authorization_url": url, "provider": "hubspot"})


@router.get("/hubspot/oauth/callback", response_class=HTMLResponse)
async def hubspot_oauth_callback(state: str = Query(...), code: str = Query(...), db: Session = Depends(get_db)):
    try:
        connection = await HubSpotOAuthService().complete(db, state=state, code=code)
        run, _, _ = _queue_hubspot_sync(db, connection, ["contact", "company", "deal"])
        result = {"type": "follei:integration-connected", "provider": "hubspot", "connection_id": str(connection.id), "run_id": str(run.id)}
    except Exception as exc:
        logger.warning("HubSpot OAuth callback failed: {}", type(exc).__name__)
        result = {"type": "follei:integration-error", "provider": "hubspot", "message": "Connection could not be completed"}
    encoded = json.dumps(result).replace("<", "\\u003c")
    target_origin = json.dumps(_settings.FRONTEND_BASE_URL.rstrip("/"))
    return HTMLResponse(f"<!doctype html><title>Follei HubSpot</title><p>You may close this window.</p><script>const result={encoded};if(window.opener)window.opener.postMessage(result,{target_origin});</script>")


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


@router.post("/hubspot/connections", response_model=CRMConnectionResponse, status_code=status.HTTP_201_CREATED, deprecated=True)
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
def run_hubspot_sync(body: HubSpotSyncRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    tenant_uuid = UUID(tenant_id)
    connection = db.query(TenantCRMConnection).filter_by(tenant_id=tenant_uuid, provider="hubspot", status="active").first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connect HubSpot for this tenant before syncing")
    try:
        run, ingestion_run, job = _queue_hubspot_sync(db, connection, list(body.resources), page_size=body.page_size, max_pages=body.max_pages_per_resource, project_now=body.project_now)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="HubSpot sync could not be queued") from exc
    return api_envelope({"id": str(run.id), "provider": run.provider, "status": run.status, "ingestion_run_id": str(ingestion_run.id), "job_id": str(job.id)})


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
