from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CreateCustomerRequest(BaseModel):
    name: str = Field(examples=["Acme Inc"])
    email: EmailStr | None = Field(default=None, examples=["admin@acme.com"])
    phone: str | None = Field(default=None, examples=["9876543210"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    status: str = Field(default="active", examples=["active"])
    plan_id: str | None = Field(default=None, examples=["77777777-7777-4777-8777-777777777777"])
    mrr: float | None = Field(default=None, examples=[999.0])
    arr: float | None = Field(default=None, examples=[11988.0])
    industry: str | None = Field(default=None, examples=["SaaS"])
    company_size: str | None = Field(default=None, examples=["51-200"])
    billing_address: dict[str, Any] = Field(default_factory=dict, examples=[{"city": "Chennai", "country": "India"}])
    custom_fields: dict[str, Any] = Field(default_factory=dict, examples=[{"account_tier": "gold"}])


class UpdateCustomerRequest(BaseModel):
    name: str | None = Field(default=None, examples=["Acme Global"])
    email: EmailStr | None = Field(default=None, examples=["success@acme.com"])
    phone: str | None = Field(default=None, examples=["9876543210"])
    status: str | None = Field(default=None, examples=["active"])
    plan_id: str | None = Field(default=None, examples=["77777777-7777-4777-8777-777777777777"])
    mrr: float | None = Field(default=None, examples=[1299.0])
    arr: float | None = Field(default=None, examples=[15588.0])
    industry: str | None = Field(default=None, examples=["SaaS"])
    company_size: str | None = Field(default=None, examples=["201-500"])
    billing_address: dict[str, Any] | None = Field(default=None, examples=[{"city": "Bengaluru", "country": "India"}])
    custom_fields: dict[str, Any] | None = Field(default=None, examples=[{"account_tier": "platinum"}])
    health_score: int | None = Field(default=None, examples=[88])
    churn_risk: str | None = Field(default=None, examples=["low"])
    expansion_score: int | None = Field(default=None, examples=[73])


class CustomerResponse(BaseModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    tenant_id: str
    status: str
    plan_id: str | None = None
    mrr: float | None = None
    arr: float | None = None
    industry: str | None = None
    company_size: str | None = None
    billing_address: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    health_score: int = 0
    churn_risk: str = "unknown"
    expansion_score: int = 0
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    conversations: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int


class CustomerContactRequest(BaseModel):
    name: str = Field(examples=["Priya Menon"])
    email: EmailStr | None = Field(default=None, examples=["priya@acme.com"])
    phone: str | None = Field(default=None, examples=["9876543210"])
    role: str | None = Field(default=None, examples=["Admin"])
    is_primary: bool = Field(default=False, examples=[True])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"department": "operations"}])


class CustomerContactResponse(BaseModel):
    id: str
    customer_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    is_primary: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class CustomerContactListResponse(BaseModel):
    items: list[CustomerContactResponse]
    total: int
    page: int
    page_size: int


class HealthScoreRequest(BaseModel):
    force_recalculate: bool = Field(default=False, examples=[True])
    model: str = Field(default="default", examples=["default"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"reason": "weekly check"}])


class HealthScoreResponse(BaseModel):
    id: str
    customer_id: str
    score: int
    model: str
    factors: dict[str, Any] = Field(default_factory=dict)
    trend: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    calculated_at: str


class HealthScoreListResponse(BaseModel):
    items: list[HealthScoreResponse]
    total: int
    page: int
    page_size: int


class CustomerEventRequest(BaseModel):
    type: str = Field(examples=["feature_used"])
    feature: str | None = Field(default=None, examples=["dashboard"])
    timestamp: datetime | None = Field(default=None, examples=["2026-07-01T10:00:00+00:00"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"count": 5}])


class CustomerEventResponse(BaseModel):
    id: str
    customer_id: str
    type: str
    feature: str | None = None
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class CustomerEventListResponse(BaseModel):
    items: list[CustomerEventResponse]
    total: int
    page: int
    page_size: int


class RenewalRequest(BaseModel):
    subscription_id: str | None = Field(default=None, examples=["dddddddd-dddd-4ddd-8ddd-dddddddddddd"])
    renewal_date: date = Field(examples=["2026-12-31"])
    expected_value: float | None = Field(default=None, examples=[25000])
    probability: float | None = Field(default=None, examples=[0.8])
    notes: str | None = Field(default=None, examples=["High renewal confidence"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateRenewalRequest(BaseModel):
    renewal_date: date | None = Field(default=None, examples=["2027-01-15"])
    expected_value: float | None = Field(default=None, examples=[28000])
    probability: float | None = Field(default=None, examples=[0.9])
    status: str | None = Field(default=None, examples=["closed_won"])
    actual_value: float | None = Field(default=None, examples=[27500])
    closed_date: date | None = Field(default=None, examples=["2026-12-20"])
    notes: str | None = Field(default=None, examples=["Renewed with expansion"])
    metadata: dict[str, Any] | None = Field(default=None, examples=[{"owner": "csm"}])


class RenewalResponse(BaseModel):
    id: str
    customer_id: str
    subscription_id: str | None = None
    renewal_date: date
    expected_value: float | None = None
    probability: float | None = None
    status: str
    actual_value: float | None = None
    closed_date: date | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class RenewalListResponse(BaseModel):
    items: list[RenewalResponse]
    total: int
    page: int
    page_size: int
