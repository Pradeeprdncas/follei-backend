from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.schemas.integration import (
    CreateIntegrationConnectionRequest,
    InboundWebhookRequest,
    InboundWebhookResponse,
    IntegrationConnectionListResponse,
    IntegrationConnectionResponse,
    IntegrationConnectionSummary,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationSummary,
    SyncJobListResponse,
    SyncJobResponse,
    SyncRequest,
    UpdateIntegrationConnectionRequest,
    WebhookEventListResponse,
    WebhookEventResponse,
    WebhookListResponse,
    WebhookRequest,
    WebhookResponse,
)

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations"])
connections_router = APIRouter(prefix="/integration-connections", tags=["Integrations"])
webhook_events_router = APIRouter(prefix="/webhook-events", tags=["Webhooks & Events"])
webhooks_receive_router = APIRouter(prefix="/webhooks", tags=["Webhooks & Events"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SALESFORCE_ID = "11111111-1111-4111-8111-111111111111"
HUBSPOT_ID = "22222222-2222-4222-8222-222222222222"
GMAIL_ID = "33333333-3333-4333-8333-333333333333"
WHATSAPP_ID = "44444444-4444-4444-8444-444444444444"

INTEGRATIONS: dict[str, IntegrationResponse] = {
    SALESFORCE_ID: IntegrationResponse(
        id=SALESFORCE_ID,
        name="Salesforce",
        category="crm",
        auth_type="oauth2",
        status="available",
        auth_url="https://login.salesforce.com/services/oauth2/authorize",
        token_url="https://login.salesforce.com/services/oauth2/token",
        scopes=["api", "refresh_token"],
        webhook_support=True,
        actions=["create_contact", "update_deal", "search_leads"],
    ),
    HUBSPOT_ID: IntegrationResponse(
        id=HUBSPOT_ID,
        name="HubSpot",
        category="crm",
        auth_type="api_key",
        status="available",
        webhook_support=True,
        actions=["create_contact", "update_deal", "search_contacts"],
    ),
    GMAIL_ID: IntegrationResponse(
        id=GMAIL_ID,
        name="Gmail",
        category="email",
        auth_type="oauth2",
        status="available",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=["gmail.send", "gmail.readonly"],
        webhook_support=False,
        actions=["send_email", "read_email"],
    ),
    WHATSAPP_ID: IntegrationResponse(
        id=WHATSAPP_ID,
        name="WhatsApp",
        category="messaging",
        auth_type="api_key",
        status="available",
        webhook_support=True,
        actions=["send_message", "send_template"],
    ),
}
CONNECTIONS: dict[str, IntegrationConnectionResponse] = {}
SYNC_JOBS: dict[str, SyncJobResponse] = {}
CONNECTION_SYNC_JOBS: dict[str, list[str]] = {}
WEBHOOKS: dict[str, WebhookResponse] = {}
CONNECTION_WEBHOOKS: dict[str, list[str]] = {}
WEBHOOK_EVENTS: dict[str, WebhookEventResponse] = {}


def _get_integration_or_404(integration_id: str) -> IntegrationResponse:
    integration = INTEGRATIONS.get(integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return integration


def _get_connection_or_404(connection_id: str) -> IntegrationConnectionResponse:
    connection = CONNECTIONS.get(connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connection not found")
    return connection


@integrations_router.get("", response_model=IntegrationListResponse)
def list_integrations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> IntegrationListResponse:
    items = [
        IntegrationSummary(
            id=item.id,
            name=item.name,
            category=item.category,
            auth_type=item.auth_type,
            status=item.status,
        )
        for item in INTEGRATIONS.values()
    ]
    total = len(items)
    start = (page - 1) * page_size
    return IntegrationListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@integrations_router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(integration_id: str) -> IntegrationResponse:
    return _get_integration_or_404(integration_id)


@connections_router.post("", response_model=IntegrationConnectionSummary, status_code=status.HTTP_201_CREATED)
def create_connection(payload: CreateIntegrationConnectionRequest) -> IntegrationConnectionSummary:
    integration = _get_integration_or_404(payload.integration_id)
    connection_id = str(uuid4())
    now = _now()
    connection = IntegrationConnectionResponse(
        id=connection_id,
        integration_id=integration.id,
        integration_name=integration.name,
        tenant_id=payload.tenant_id,
        status="connected",
        connected_at=now,
        last_sync=None,
        integration={"id": integration.id, "name": integration.name},
        auth_type=payload.auth_type,
        settings=payload.settings,
        sync_jobs=[],
    )
    CONNECTIONS[connection_id] = connection
    return IntegrationConnectionSummary(**connection.model_dump(exclude={"integration", "auth_type", "settings", "sync_jobs"}))


@connections_router.get("", response_model=IntegrationConnectionListResponse)
def list_connections(
    tenant_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> IntegrationConnectionListResponse:
    items = [
        IntegrationConnectionSummary(**item.model_dump(exclude={"integration", "auth_type", "settings", "sync_jobs"}))
        for item in CONNECTIONS.values()
        if tenant_id is None or item.tenant_id == tenant_id
    ]
    total = len(items)
    start = (page - 1) * page_size
    return IntegrationConnectionListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@connections_router.get("/{connection_id}", response_model=IntegrationConnectionResponse)
def get_connection(connection_id: str) -> IntegrationConnectionResponse:
    connection = _get_connection_or_404(connection_id)
    job_ids = CONNECTION_SYNC_JOBS.get(connection_id, [])
    jobs = [SYNC_JOBS[job_id].model_dump() for job_id in job_ids if job_id in SYNC_JOBS]
    return connection.model_copy(update={"sync_jobs": jobs})


@connections_router.patch("/{connection_id}", response_model=IntegrationConnectionResponse)
def update_connection(connection_id: str, payload: UpdateIntegrationConnectionRequest) -> IntegrationConnectionResponse:
    connection = _get_connection_or_404(connection_id)
    data = payload.model_dump(exclude_unset=True)
    if "settings" in data and data["settings"] is not None:
        data["settings"] = {**connection.settings, **data["settings"]}
    updated = connection.model_copy(update=data)
    CONNECTIONS[connection_id] = updated
    return updated


@connections_router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str) -> Response:
    _get_connection_or_404(connection_id)
    CONNECTIONS.pop(connection_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@connections_router.post("/{connection_id}/sync", response_model=SyncJobResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(connection_id: str, payload: SyncRequest) -> SyncJobResponse:
    connection = _get_connection_or_404(connection_id)
    job_id = str(uuid4())
    job = SyncJobResponse(
        id=job_id,
        job_id=job_id,
        connection_id=connection_id,
        status="queued",
        sync_type=payload.sync_type,
        entities=payload.entities,
        records_synced=0,
        started_at=_now(),
        completed_at=None,
    )
    SYNC_JOBS[job_id] = job
    CONNECTION_SYNC_JOBS.setdefault(connection_id, []).append(job_id)
    CONNECTIONS[connection_id] = connection.model_copy(update={"last_sync": job.started_at})
    return job


@connections_router.get("/{connection_id}/sync-jobs", response_model=SyncJobListResponse)
def list_sync_jobs(
    connection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SyncJobListResponse:
    _get_connection_or_404(connection_id)
    items = [SYNC_JOBS[job_id] for job_id in CONNECTION_SYNC_JOBS.get(connection_id, []) if job_id in SYNC_JOBS]
    total = len(items)
    start = (page - 1) * page_size
    return SyncJobListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@connections_router.post("/{connection_id}/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(connection_id: str, payload: WebhookRequest) -> WebhookResponse:
    _get_connection_or_404(connection_id)
    webhook_id = str(uuid4())
    webhook = WebhookResponse(
        id=webhook_id,
        connection_id=connection_id,
        event_type=payload.event_type,
        url=payload.url,
        active=payload.active,
        created_at=_now(),
    )
    WEBHOOKS[webhook_id] = webhook
    CONNECTION_WEBHOOKS.setdefault(connection_id, []).append(webhook_id)
    return webhook


@connections_router.get("/{connection_id}/webhooks", response_model=WebhookListResponse)
def list_webhooks(
    connection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> WebhookListResponse:
    _get_connection_or_404(connection_id)
    items = [WEBHOOKS[webhook_id] for webhook_id in CONNECTION_WEBHOOKS.get(connection_id, []) if webhook_id in WEBHOOKS]
    total = len(items)
    start = (page - 1) * page_size
    return WebhookListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@connections_router.delete("/{connection_id}/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(connection_id: str, webhook_id: str) -> Response:
    _get_connection_or_404(connection_id)
    webhook = WEBHOOKS.get(webhook_id)
    if webhook is None or webhook.connection_id != connection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    WEBHOOKS.pop(webhook_id, None)
    CONNECTION_WEBHOOKS[connection_id] = [item_id for item_id in CONNECTION_WEBHOOKS.get(connection_id, []) if item_id != webhook_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@webhooks_receive_router.post("/receive/{integration_id}", response_model=InboundWebhookResponse)
def receive_webhook(integration_id: str, payload: InboundWebhookRequest) -> InboundWebhookResponse:
    _get_integration_or_404(integration_id)
    event_id = str(uuid4())
    event = WebhookEventResponse(
        id=event_id,
        integration_id=integration_id,
        event_type=payload.event_type,
        payload=payload.payload,
        status="processed",
        created_at=payload.timestamp or _now(),
    )
    WEBHOOK_EVENTS[event_id] = event
    return InboundWebhookResponse(received=True, event_id=event_id)


@webhook_events_router.get("", response_model=WebhookEventListResponse)
def list_webhook_events(
    event_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> WebhookEventListResponse:
    items = list(WEBHOOK_EVENTS.values())
    if event_type is not None:
        items = [item for item in items if item.event_type == event_type]
    if status_filter is not None:
        items = [item for item in items if item.status == status_filter]
    total = len(items)
    start = (page - 1) * page_size
    return WebhookEventListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)
