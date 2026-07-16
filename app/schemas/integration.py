from typing import Any

from pydantic import BaseModel, Field


class IntegrationSummary(BaseModel):
    id: str
    name: str
    category: str
    auth_type: str
    status: str


class IntegrationListResponse(BaseModel):
    items: list[IntegrationSummary]
    total: int
    page: int
    page_size: int


class IntegrationResponse(IntegrationSummary):
    auth_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    webhook_support: bool = False
    actions: list[str] = Field(default_factory=list)


class CreateIntegrationConnectionRequest(BaseModel):
    integration_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    tenant_id: str = Field(examples=["22222222-2222-4222-8222-222222222222"])
    auth_type: str = Field(examples=["oauth2"])
    credentials: dict[str, Any] = Field(default_factory=dict, examples=[{"access_token": "oauth_token"}])
    settings: dict[str, Any] = Field(default_factory=dict, examples=[{"sync_frequency": "hourly"}])


class UpdateIntegrationConnectionRequest(BaseModel):
    credentials: dict[str, Any] | None = Field(default=None, examples=[{"access_token": "new_token"}])
    settings: dict[str, Any] | None = Field(default=None, examples=[{"sync_frequency": "daily"}])
    status: str | None = Field(default=None, examples=["connected"])


class IntegrationConnectionSummary(BaseModel):
    id: str
    integration_id: str
    integration_name: str
    tenant_id: str
    status: str
    connected_at: str
    last_sync: str | None = None


class IntegrationConnectionResponse(IntegrationConnectionSummary):
    integration: dict[str, Any]
    auth_type: str
    settings: dict[str, Any] = Field(default_factory=dict)
    sync_jobs: list[dict[str, Any]] = Field(default_factory=list)


class IntegrationConnectionListResponse(BaseModel):
    items: list[IntegrationConnectionSummary]
    total: int
    page: int
    page_size: int


class SyncRequest(BaseModel):
    sync_type: str = Field(default="incremental", examples=["full"])
    entities: list[str] = Field(default_factory=list, examples=[["contacts", "deals"]])


class SyncJobResponse(BaseModel):
    id: str
    job_id: str
    connection_id: str
    status: str
    sync_type: str
    entities: list[str] = Field(default_factory=list)
    records_synced: int = 0
    started_at: str
    completed_at: str | None = None


class SyncJobListResponse(BaseModel):
    items: list[SyncJobResponse]
    total: int
    page: int
    page_size: int


class WebhookRequest(BaseModel):
    event_type: str = Field(examples=["lead.created"])
    url: str = Field(examples=["https://api.follei.com/webhooks/salesforce"])
    secret: str | None = Field(default=None, examples=["webhook_secret"])
    active: bool = Field(default=True, examples=[True])


class WebhookResponse(BaseModel):
    id: str
    connection_id: str
    event_type: str
    url: str
    active: bool
    created_at: str


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]
    total: int
    page: int
    page_size: int


class InboundWebhookRequest(BaseModel):
    event_type: str = Field(examples=["lead.created"])
    payload: dict[str, Any] = Field(default_factory=dict, examples=[{"email": "lead@company.com"}])
    timestamp: str | None = Field(default=None, examples=["2026-06-15T14:00:00Z"])


class InboundWebhookResponse(BaseModel):
    received: bool
    event_id: str


class WebhookEventResponse(BaseModel):
    id: str
    integration_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: str


class WebhookEventListResponse(BaseModel):
    items: list[WebhookEventResponse]
    total: int
    page: int
    page_size: int
