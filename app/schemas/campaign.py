"""Campaign Schemas - Pydantic models for campaign API."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import enum


class CampaignType(str, enum.Enum):
    """Campaign channel types."""
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VOICE = "voice"
    MULTI_CHANNEL = "multi_channel"


class CampaignStatus(str, enum.Enum):
    """Campaign lifecycle states."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class DeliveryStatus(str, enum.Enum):
    """Message delivery status."""
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    REPLIED = "replied"
    UNSUBSCRIBED = "unsubscribed"


class CampaignCreateRequest(BaseModel):
    """Request to create a campaign."""
    name: str = Field(examples=["June Offer Campaign"])
    description: Optional[str] = Field(default=None, examples=["Summer sale promotion"])
    type: CampaignType = Field(examples=[CampaignType.EMAIL])
    subject: Optional[str] = Field(default=None, examples=["Special Offer Inside!"])
    body: str = Field(examples=["Check out our latest offers..."])
    image_url: Optional[str] = Field(default=None, examples=["https://example.com/image.jpg"])
    start_date: Optional[datetime] = Field(default=None, examples=["2024-06-01T00:00:00Z"])
    end_date: Optional[datetime] = Field(default=None, examples=["2024-06-30T23:59:59Z"])
    schedule_config: dict[str, Any] | None = Field(default=None, examples=[{"send_immediately": True, "timezone": "UTC"}])
    target_audience: dict[str, Any] | None = Field(default=None, examples=[{"filters": {"status": ["new", "qualified"]}, "manual_lead_ids": []}])
    tracking_config: dict[str, Any] | None = Field(default=None, examples=[{"opens": True, "clicks": True, "replies": True}])
    metadata_: dict[str, Any] | None = Field(default=None, examples=[{"source": "manual"}])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])


class CampaignUpdateRequest(BaseModel):
    """Request to update a campaign."""
    name: Optional[str] = Field(default=None, examples=["Updated Campaign"])
    description: Optional[str] = Field(default=None)
    subject: Optional[str] = Field(default=None)
    body: Optional[str] = Field(default=None)
    image_url: Optional[str] = Field(default=None)
    start_date: Optional[datetime] = Field(default=None)
    end_date: Optional[datetime] = Field(default=None)
    schedule_config: dict[str, Any] | None = Field(default=None)
    target_audience: dict[str, Any] | None = Field(default=None)
    tracking_config: dict[str, Any] | None = Field(default=None)
    metadata_: dict[str, Any] | None = Field(default=None)
    status: Optional[CampaignStatus] = Field(default=None)


class CampaignResponse(BaseModel):
    """Campaign response."""
    id: str
    name: str
    description: Optional[str] = None
    type: CampaignType
    status: CampaignStatus
    subject: Optional[str] = None
    body: str
    image_url: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    schedule_config: dict[str, Any] | None = None
    target_audience: dict[str, Any] | None = None
    tracking_config: dict[str, Any] | None = None
    analytics: dict[str, Any] | None = None
    metadata_: dict[str, Any] | None = None
    total_recipients: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0
    failed_count: int = 0
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class CampaignListResponse(BaseModel):
    """List of campaigns."""
    items: List[CampaignResponse]
    total: int
    page: int
    page_size: int


class CampaignMessageResponse(BaseModel):
    """Campaign message response."""
    id: str
    campaign_id: str
    lead_id: str
    channel: CampaignType
    recipient: str
    subject: Optional[str] = None
    body: str
    image_url: Optional[str] = None
    status: DeliveryStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime


class CampaignStatsResponse(BaseModel):
    """Campaign statistics."""
    campaign_id: str
    total_recipients: int
    sent: int
    delivered: int
    opened: int
    clicked: int
    replied: int
    bounced: int = 0
    failed: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    reply_rate: float


class CampaignSendRequest(BaseModel):
    subject: str
    body: str
    provider: str = "gmail"
    dry_run: bool = False


class CampaignSendRecipient(BaseModel):
    lead_id: str
    email: Optional[str] = None
    status: str
    message_id: Optional[str] = None
    detail: Optional[str] = None


class CampaignSendResponse(BaseModel):
    campaign_id: str
    tenant_id: str
    provider: str
    dry_run: bool
    sent: int
    skipped: int
    recipients: List[CampaignSendRecipient]
    sent_at: datetime


class CampaignInboundEmailResponse(BaseModel):
    id: str
    tenant_id: str
    campaign_id: Optional[str] = None
    lead_id: Optional[str] = None
    from_email: Optional[str] = None
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    provider: str = "brevo"
    event_type: str = "inbound"
    raw_payload: Dict[str, Any] = {}
    received_at: datetime


class CampaignInboundEmailListResponse(BaseModel):
    items: List[CampaignInboundEmailResponse]
    total: int
    page: int
    page_size: int


class CampaignInboundWebhookResponse(BaseModel):
    received: bool
    inbound_email: CampaignInboundEmailResponse


class CampaignMetricBase(BaseModel):
    campaign_id: str
    metric_type: str
    value: float = 0
    metadata_: Optional[Dict[str, Any]] = None


class CampaignMetricCreate(CampaignMetricBase):
    tenant_id: str


class CampaignMetricResponse(CampaignMetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    recorded_at: datetime