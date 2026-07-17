from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, Field

from app.domains.messaging.constants import MessageStatus, MessageDirection, Channel


class MessageSendRequest(BaseModel):
    channel: Channel
    recipient: str
    subject: str | None = None
    body: str
    html_body: str | None = None
    sender_name: str | None = None
    tenant_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    id: str
    public_id: str
    tenant_id: str | None = None
    conversation_id: str | None = None
    channel: str | None = None
    direction: str | None = None
    role: str | None = None
    content: str | None = None
    message: str | None = None
    message_type: str | None = None
    metadata: dict[str, Any] | None = None
    delivery_status: list[dict[str, Any]] | None = None
    created_at: datetime | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int


class HealthStatus(BaseModel):
    email: str
    whatsapp: str
    sms: str


class HealthResponse(BaseModel):
    status: str
    providers: HealthStatus


class DeliveryStatusResponse(BaseModel):
    id: str
    status: str
    provider: str | None = None
    delivered_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
