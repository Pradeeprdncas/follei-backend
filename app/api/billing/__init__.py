"""Billing router — delegates to BillingService."""
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.billing_service import BillingService
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/billing", tags=["Billing"])


class PlanIn(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = 0
    currency: str = "USD"
    billing_period: str = "monthly"
    features: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)


class SubscriptionIn(BaseModel):
    tenant_id: UUID
    plan_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    status: str = "active"
    start_date: Optional[date] = None
    billing_cycle: str = "monthly"
    payment_method_id: Optional[UUID] = None


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[UUID] = None
    status: Optional[str] = None


class InvoiceIn(BaseModel):
    subscription_id: Optional[UUID] = None
    tenant_id: UUID
    items: list[dict[str, Any]] = Field(default_factory=list)
    due_date: Optional[date] = None
    currency: str = "USD"


class PaymentIn(BaseModel):
    invoice_id: Optional[UUID] = None
    tenant_id: UUID
    amount: float
    currency: str = "USD"
    payment_method: str = "card"
    transaction_id: Optional[str] = None


def _billing(db: Session = Depends(get_db)) -> BillingService:
    return BillingService(db)


@router.post("/plans")
def create_plan(payload: PlanIn, svc: BillingService = Depends(_billing)):
    return svc.create_plan(**payload.model_dump())


@router.get("/plans")
def list_plans(svc: BillingService = Depends(_billing)):
    return svc.list_plans()


@router.get("/plans/{plan_id}")
def get_plan(plan_id: UUID, svc: BillingService = Depends(_billing)):
    return svc.get_plan(plan_id)


@router.post("/subscriptions")
def create_subscription(payload: SubscriptionIn, svc: BillingService = Depends(_billing), current_user=Depends(get_current_user)):
    return svc.create_subscription(**payload.model_dump())


@router.get("/subscriptions/{subscription_id}")
def get_subscription(subscription_id: UUID, svc: BillingService = Depends(_billing)):
    return svc.get_subscription(subscription_id)


@router.patch("/subscriptions/{subscription_id}")
def update_subscription(subscription_id: UUID, payload: SubscriptionUpdate, svc: BillingService = Depends(_billing)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    return svc.update_subscription(subscription_id, **updates)


@router.post("/invoices")
def create_invoice(payload: InvoiceIn, svc: BillingService = Depends(_billing), current_user=Depends(get_current_user)):
    return svc.create_invoice(**payload.model_dump())


@router.get("/invoices")
def list_invoices(tenant_id: UUID, svc: BillingService = Depends(_billing)):
    return svc.list_invoices(tenant_id)


@router.post("/payments")
def record_payment(payload: PaymentIn, svc: BillingService = Depends(_billing)):
    return svc.record_payment(**payload.model_dump())
