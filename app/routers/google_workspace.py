"""Frontend-friendly Google Workspace connector endpoints."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.kafka import ensure_topics, get_producer
from app.config.settings import get_settings
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.integrations.oauth_connection import GoogleWorkspaceConnection
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.schemas.api_envelope import api_envelope
from app.services.integrations.google_workspace import DEFAULT_RESOURCES, GoogleWorkspaceError, GoogleWorkspaceOAuthService, RESOURCE_SCOPES


router = APIRouter(prefix="/api/v1/integrations/google-workspace", tags=["Google Workspace"])
_settings = get_settings()


class GoogleConnectRequest(BaseModel):
    resources: list[str] = Field(default_factory=lambda: list(DEFAULT_RESOURCES))


class GoogleSyncRequest(BaseModel):
    resources: list[str] | None = None


def _queue_sync(db: Session, connection: GoogleWorkspaceConnection, resources: list[str]):
    selected = list(dict.fromkeys(resources))
    invalid = sorted(set(selected) - set(RESOURCE_SCOPES))
    if invalid or not selected:
        raise HTTPException(status_code=422, detail=f"Invalid Google resources: {invalid or 'none selected'}")
    if not connection.source_id:
        raise HTTPException(status_code=409, detail="Google Workspace knowledge source is missing; reconnect the account")
    run = IngestionRun(id=uuid4(), tenant_id=connection.tenant_id, source_id=connection.source_id, status="queued")
    jobs = [
        SourceIngestionJob(
            id=uuid4(), tenant_id=connection.tenant_id, run_id=run.id,
            job_type=f"google_{resource}_sync", target=connection.email_address,
            status="queued", payload={"connection_id": str(connection.id), "resource": resource},
        )
        for resource in selected
    ]
    db.add_all([run, *jobs]); db.commit()
    ensure_topics(); producer = get_producer()
    for job, resource in zip(jobs, selected):
        producer.send(_settings.KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC, key=str(job.id), value={
            "job_id": str(job.id), "run_id": str(run.id), "source_id": str(run.source_id),
            "connection_id": str(connection.id), "tenant_id": str(connection.tenant_id), "resource": resource,
        })
    producer.flush()
    return run, jobs


@router.post("/oauth/start")
def oauth_start(payload: GoogleConnectRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id), user_id: str = Depends(get_authenticated_user_id)):
    try:
        url = GoogleWorkspaceOAuthService().create_authorization_url(db, tenant_id=tenant_id, user_id=user_id, resources=payload.resources)
    except GoogleWorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return api_envelope({"authorization_url": url, "resources": payload.resources, "scopes": [RESOURCE_SCOPES[item] for item in payload.resources]})


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(state: str = Query(...), code: str = Query(...), db: Session = Depends(get_db)):
    try:
        connection, run, jobs = await GoogleWorkspaceOAuthService().complete_authorization(db, state=state, code=code)
        ensure_topics()
        producer = get_producer()
        for job in jobs:
            producer.send(_settings.KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC, key=str(job.id), value={
                "job_id": str(job.id), "run_id": str(run.id), "source_id": str(run.source_id),
                "connection_id": str(connection.id), "tenant_id": str(connection.tenant_id),
                "resource": (job.payload or {}).get("resource"),
            })
        producer.flush()
        payload = {"type": "follei:integration-connected", "provider": "google_workspace", "connection_id": str(connection.id), "run_id": str(run.id)}
    except Exception as exc:
        payload = {"type": "follei:integration-error", "provider": "google_workspace", "message": str(exc)}
    encoded = json.dumps(payload).replace("<", "\\u003c")
    return HTMLResponse(f"<!doctype html><title>Follei Google Workspace</title><p>You may close this window.</p><script>const result={encoded};if(window.opener)window.opener.postMessage(result,window.location.origin);</script>")


@router.get("/connections")
def connections(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    rows = db.query(GoogleWorkspaceConnection).filter(GoogleWorkspaceConnection.tenant_id == UUID(tenant_id)).all()
    return api_envelope({"connections": [{"id": str(row.id), "email": row.email_address, "status": row.status, "resources": row.enabled_resources, "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None, "last_error": row.last_error} for row in rows]})


@router.post("/connections/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_connection(
    connection_id: UUID,
    payload: GoogleSyncRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    connection = db.query(GoogleWorkspaceConnection).filter(
        GoogleWorkspaceConnection.id == connection_id,
        GoogleWorkspaceConnection.tenant_id == UUID(tenant_id),
        GoogleWorkspaceConnection.status == "active",
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Google Workspace connection not found")
    try:
        run, jobs = _queue_sync(db, connection, payload.resources or list(connection.enabled_resources or []))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Google Workspace sync could not be queued") from exc
    return api_envelope({
        "connection_id": str(connection.id), "run_id": str(run.id), "status": run.status,
        "jobs": [{"id": str(job.id), "type": job.job_type, "status": job.status} for job in jobs],
    }, accepted=True)
