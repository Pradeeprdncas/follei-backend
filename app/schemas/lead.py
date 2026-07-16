from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CreateLeadRequest(BaseModel):
    email: EmailStr = Field(examples=["lead@example.com"])
    full_name: str | None = Field(default=None, examples=["Ravi Sharma"])
    company: str | None = Field(default=None, examples=["Acme Inc"])
    phone: str | None = Field(default=None, examples=["9876543210"])
    source: str | None = Field(default=None, examples=["website"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    status: str = Field(default="new", examples=["new"])
    priority: str | None = Field(default=None, examples=["high"])
    tags: list[str] = Field(default_factory=list, examples=[["demo", "pricing"]])
    custom_fields: dict[str, Any] = Field(default_factory=dict, examples=[{"budget": "5000"}])
    assigned_to: str | None = Field(default=None, examples=["66666666-6666-4666-8666-666666666666"])


class UpdateLeadRequest(BaseModel):
    email: EmailStr | None = Field(default=None, examples=["lead.updated@example.com"])
    full_name: str | None = Field(default=None, examples=["Ravi Sharma"])
    company: str | None = Field(default=None, examples=["Acme Inc"])
    phone: str | None = Field(default=None, examples=["9876543210"])
    source: str | None = Field(default=None, examples=["referral"])
    status: str | None = Field(default=None, examples=["qualified"])
    priority: str | None = Field(default=None, examples=["medium"])
    tags: list[str] | None = Field(default=None, examples=[["qualified"]])
    custom_fields: dict[str, Any] | None = Field(default=None, examples=[{"budget": "10000"}])
    assigned_to: str | None = Field(default=None, examples=["66666666-6666-4666-8666-666666666666"])
    score: int | None = Field(default=None, examples=[82])


class LeadResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    company: str | None = None
    phone: str | None = None
    source: str | None = None
    tenant_id: str
    status: str
    priority: str | None = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    assigned_to: str | None = None
    score: int = 0
    created_at: str
    updated_at: str


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    page_size: int


class LeadActivityRequest(BaseModel):
    type: str = Field(examples=["call"])
    description: str | None = Field(default=None, examples=["Discovery call completed"])
    outcome: str | None = Field(default=None, examples=["interested"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"duration_minutes": 30}])


class LeadActivityResponse(BaseModel):
    id: str
    lead_id: str
    type: str
    description: str | None = None
    outcome: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class LeadActivityListResponse(BaseModel):
    items: list[LeadActivityResponse]
    total: int
    page: int
    page_size: int


class LeadScoreRequest(BaseModel):
    model: str = Field(default="default", examples=["default"])
    force_recalculate: bool = Field(default=False, examples=[True])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"reason": "new activity"}])


class LeadScoreResponse(BaseModel):
    id: str
    lead_id: str
    score: int
    model: str
    factors: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    calculated_at: str


class LeadScoreListResponse(BaseModel):
    items: list[LeadScoreResponse]
    total: int
    page: int
    page_size: int


class QualificationFrameworkRequest(BaseModel):
    name: str = Field(examples=["BANT"])
    description: str | None = Field(default=None, examples=["Budget, Authority, Need, Timeline framework"])
    criteria: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"name": "budget", "weight": 25}]])
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualificationFrameworkResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class QualificationFrameworkListResponse(BaseModel):
    items: list[QualificationFrameworkResponse]
    total: int
    page: int
    page_size: int


class LeadQualificationRequest(BaseModel):
    framework_id: str = Field(examples=["99999999-9999-4999-8999-999999999999"])
    answers: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"question": "Budget?", "answer": "Yes"}]])
    status: str = Field(default="completed", examples=["completed"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class LeadQualificationResponse(BaseModel):
    id: str
    lead_id: str
    framework_id: str
    answers: list[dict[str, Any]] = Field(default_factory=list)
    score: int
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class LeadQualificationListResponse(BaseModel):
    items: list[LeadQualificationResponse]
    total: int
    page: int
    page_size: int


class OpportunityRequest(BaseModel):
    lead_id: str | None = Field(default=None, examples=["22222222-2222-4222-8222-222222222222"])
    name: str = Field(examples=["Acme annual subscription"])
    value: float = Field(default=0, examples=[25000])
    currency: str = Field(default="USD", examples=["USD"])
    stage: str = Field(default="discovery", examples=["proposal"])
    probability: float = Field(default=0, examples=[0.65])
    expected_close_date: date | None = Field(default=None, examples=["2026-07-30"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateOpportunityRequest(BaseModel):
    name: str | None = Field(default=None, examples=["Acme annual expansion"])
    value: float | None = Field(default=None, examples=[30000])
    currency: str | None = Field(default=None, examples=["USD"])
    stage: str | None = Field(default=None, examples=["negotiation"])
    probability: float | None = Field(default=None, examples=[0.75])
    expected_close_date: date | None = Field(default=None, examples=["2026-08-15"])
    metadata: dict[str, Any] | None = Field(default=None, examples=[{"next_step": "legal review"}])


class OpportunityResponse(BaseModel):
    id: str
    lead_id: str | None = None
    name: str
    value: float
    currency: str
    stage: str
    probability: float
    expected_close_date: date | None = None
    tenant_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int


class ProposalRequest(BaseModel):
    template_id: str | None = Field(default=None, examples=["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"])
    title: str | None = Field(default=None, examples=["Acme proposal"])
    customizations: dict[str, Any] = Field(default_factory=dict, examples=[{"discount": "10%"}])


class ProposalResponse(BaseModel):
    id: str
    opportunity_id: str
    document_id: str
    template_id: str | None = None
    title: str | None = None
    status: str
    customizations: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class QuoteRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"name": "Pro plan", "quantity": 10, "price": 99}]])
    valid_until: date | None = Field(default=None, examples=["2026-07-31"])
    terms: str | None = Field(default=None, examples=["Net 30"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuoteResponse(BaseModel):
    id: str
    opportunity_id: str
    status: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    valid_until: date | None = None
    terms: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    total: float
    created_at: str


class MeetingRequest(BaseModel):
    lead_id: str | None = Field(default=None, examples=["22222222-2222-4222-8222-222222222222"])
    opportunity_id: str | None = Field(default=None, examples=["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"])
    title: str = Field(examples=["Product demo"])
    start_time: datetime = Field(examples=["2026-07-01T10:00:00+00:00"])
    end_time: datetime = Field(examples=["2026-07-01T10:30:00+00:00"])
    timezone: str | None = Field(default=None, examples=["Asia/Kolkata"])
    attendees: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"email": "lead@example.com"}]])
    location: str | None = Field(default=None, examples=["Google Meet"])
    calendar_event_id: str | None = Field(default=None, examples=["cccccccc-cccc-4ccc-8ccc-cccccccccccc"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateMeetingRequest(BaseModel):
    title: str | None = Field(default=None, examples=["Updated product demo"])
    start_time: datetime | None = Field(default=None, examples=["2026-07-01T11:00:00+00:00"])
    end_time: datetime | None = Field(default=None, examples=["2026-07-01T11:30:00+00:00"])
    status: str | None = Field(default=None, examples=["completed"])
    notes: str | None = Field(default=None, examples=["Customer wants pricing"])
    metadata: dict[str, Any] | None = Field(default=None, examples=[{"recording_url": "https://example.com/recording"}])


class MeetingResponse(BaseModel):
    id: str
    lead_id: str | None = None
    opportunity_id: str | None = None
    title: str
    start_time: datetime
    end_time: datetime
    timezone: str | None = None
    attendees: list[dict[str, Any]] = Field(default_factory=list)
    location: str | None = None
    calendar_event_id: str | None = None
    status: str
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]
    total: int
    page: int
    page_size: int
