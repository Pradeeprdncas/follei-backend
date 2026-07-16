from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.domain import Credit, CreditTransaction, Invoice, Payment, Plan, Subscription
from app.models.tenancy import User
from app.routers.auth import get_current_user

plans_router = APIRouter(prefix="/plans", tags=["Billing"])
subscriptions_router = APIRouter(prefix="/subscriptions", tags=["Billing"])
invoices_router = APIRouter(prefix="/invoices", tags=["Billing"])
payments_router = APIRouter(prefix="/payments", tags=["Billing"])
credits_router = APIRouter(prefix="/credits", tags=["Billing"])


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
    amount: float
    currency: str = "USD"
    method: str
    stripe_payment_intent_id: Optional[str] = None


class CreditTxIn(BaseModel):
    type: str
    amount: float
    currency: str = "USD"
    description: Optional[str] = None


def _ensure_tenant(user: User, tenant_id: UUID) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _plan_payload(plan: Plan) -> dict[str, Any]:
    feature_limits = plan.feature_limits or {}
    return {"id": plan.id, "name": plan.name, "description": plan.description, "price": float(plan.price), "currency": plan.currency, "billing_period": plan.billing_interval, "features": feature_limits.get("features", []), "limits": feature_limits.get("limits", {})}


@plans_router.post("", status_code=201)
def create_plan(payload: PlanIn, db: Session = Depends(get_db)):
    plan = Plan(name=payload.name, description=payload.description, price=payload.price, currency=payload.currency, billing_interval=payload.billing_period, feature_limits={"features": payload.features, "limits": payload.limits})
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_payload(plan)


@plans_router.get("")
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.created_at.desc()).all()
    return {"items": [_plan_payload(plan) for plan in plans]}


@subscriptions_router.post("", status_code=201)
def create_subscription(payload: SubscriptionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    plan = db.get(Plan, payload.plan_id) if payload.plan_id else None
    subscription = Subscription(tenant_id=user.tenant_id, plan_id=payload.plan_id, customer_id=payload.customer_id, plan_name=plan.name if plan else "custom", status=payload.status, current_period_start=datetime.combine(payload.start_date, datetime.min.time()) if payload.start_date else None, metadata_={"billing_cycle": payload.billing_cycle, "payment_method_id": str(payload.payment_method_id) if payload.payment_method_id else None})
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return {"id": subscription.id, "plan": subscription.plan_name, "status": subscription.status, "mrr": float(plan.price) if plan else 0}


@subscriptions_router.get("")
def list_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscriptions = db.query(Subscription).filter(Subscription.tenant_id == user.tenant_id).order_by(Subscription.created_at.desc()).all()
    return {"items": [{"id": item.id, "plan": item.plan_name, "status": item.status, "mrr": 0} for item in subscriptions]}


@subscriptions_router.patch("/{subscription_id}")
def update_subscription(subscription_id: UUID, payload: SubscriptionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id, Subscription.tenant_id == user.tenant_id).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if payload.plan_id is not None:
        plan = db.get(Plan, payload.plan_id)
        subscription.plan_id = payload.plan_id
        subscription.plan_name = plan.name if plan else subscription.plan_name
    if payload.status is not None:
        subscription.status = payload.status
    db.commit()
    db.refresh(subscription)
    return {"id": subscription.id, "plan": subscription.plan_name, "status": subscription.status}


@invoices_router.post("", status_code=201)
def create_invoice(payload: InvoiceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    amount = sum(float(item.get("amount", 0)) * float(item.get("quantity", 1)) for item in payload.items)
    invoice = Invoice(tenant_id=user.tenant_id, subscription_id=payload.subscription_id, amount=amount, currency=payload.currency, due_date=payload.due_date, metadata_={"items": payload.items})
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return {"id": invoice.id, "amount": float(invoice.amount), "status": invoice.status, "due_date": invoice.due_date, "currency": invoice.currency, "items": invoice.metadata_.get("items", [])}


@invoices_router.get("")
def list_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(Invoice).filter(Invoice.tenant_id == user.tenant_id).order_by(Invoice.created_at.desc()).all()
    return {"items": [{"id": item.id, "amount": float(item.amount), "status": item.status, "due_date": item.due_date} for item in invoices]}


@payments_router.post("", status_code=201)
def create_payment(payload: PaymentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == payload.invoice_id, Invoice.tenant_id == user.tenant_id).first() if payload.invoice_id else None
    payment = Payment(tenant_id=user.tenant_id, invoice_id=payload.invoice_id, customer_id=invoice.customer_id if invoice else None, amount=payload.amount, currency=payload.currency, status="succeeded", provider=payload.method, provider_payment_id=payload.stripe_payment_intent_id, paid_at=datetime.utcnow())
    db.add(payment)
    if invoice:
        invoice.status = "paid"
        invoice.paid_at = payment.paid_at
    db.commit()
    db.refresh(payment)
    return {"id": payment.id, "amount": float(payment.amount), "status": payment.status, "method": payment.provider}


@payments_router.get("")
def list_payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payments = db.query(Payment).filter(Payment.tenant_id == user.tenant_id).order_by(Payment.created_at.desc()).all()
    return {"items": [{"id": item.id, "amount": float(item.amount), "status": item.status, "method": item.provider} for item in payments]}


def _get_or_create_credit(db: Session, user: User, currency: str = "USD") -> Credit:
    credit = db.query(Credit).filter(Credit.tenant_id == user.tenant_id).first()
    if credit:
        return credit
    credit = Credit(tenant_id=user.tenant_id, balance=0, currency=currency)
    db.add(credit)
    db.flush()
    return credit


@credits_router.get("")
def get_credits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    credit = _get_or_create_credit(db, user)
    db.commit()
    db.refresh(credit)
    return {"tenant_id": user.tenant_id, "balance": float(credit.balance), "currency": credit.currency, "last_updated": credit.updated_at}


@credits_router.post("/transactions", status_code=201)
def create_credit_transaction(payload: CreditTxIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    credit = _get_or_create_credit(db, user, payload.currency)
    delta = payload.amount if payload.type in {"purchase", "add", "credit"} else -payload.amount
    credit.balance = float(credit.balance) + delta
    credit.currency = payload.currency
    tx = CreditTransaction(tenant_id=user.tenant_id, credit_id=credit.id, transaction_type=payload.type, amount=payload.amount, balance_after=credit.balance, metadata_={"description": payload.description})
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {"id": tx.id, "type": tx.transaction_type, "amount": float(tx.amount), "currency": credit.currency, "balance_after": float(tx.balance_after), "description": tx.metadata_.get("description")}
