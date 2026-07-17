"""Billing service."""
from uuid import UUID
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.domain import Plan, Subscription, Invoice, Payment, Credit, CreditTransaction


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.plan_repo = BaseRepository(db, Plan)
        self.subscription_repo = BaseRepository(db, Subscription)
        self.invoice_repo = BaseRepository(db, Invoice)
        self.payment_repo = BaseRepository(db, Payment)

    def create_plan(self, **kwargs) -> Plan:
        plan = Plan(**kwargs)
        return self.plan_repo.create(plan)

    def get_plan(self, plan_id: UUID) -> Plan:
        plan = self.plan_repo.get_by_id(plan_id)
        if not plan:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan

    def list_plans(self) -> list[Plan]:
        return self.plan_repo.list_all()

    def create_subscription(self, **kwargs) -> Subscription:
        sub = Subscription(**kwargs)
        return self.subscription_repo.create(sub)

    def get_subscription(self, subscription_id: UUID) -> Subscription:
        sub = self.subscription_repo.get_by_id(subscription_id)
        if not sub:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Subscription not found")
        return sub

    def update_subscription(self, subscription_id: UUID, **kwargs) -> Subscription:
        sub = self.subscription_repo.update(subscription_id, **kwargs)
        if not sub:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Subscription not found")
        return sub

    def create_invoice(self, **kwargs) -> Invoice:
        inv = Invoice(**kwargs)
        return self.invoice_repo.create(inv)

    def list_invoices(self, tenant_id: UUID) -> list[Invoice]:
        return self.invoice_repo.get_by_tenant(tenant_id)

    def record_payment(self, **kwargs) -> Payment:
        pmt = Payment(**kwargs)
        return self.payment_repo.create(pmt)
