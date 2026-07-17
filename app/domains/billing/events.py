"""Billing domain events."""
def build_subscription_created_event(subscription_id: str, tenant_id: str, plan_name: str) -> dict:
    return {"subscription_id": subscription_id, "tenant_id": tenant_id, "plan_name": plan_name}


def build_payment_received_event(payment_id: str, tenant_id: str, amount: float, currency: str) -> dict:
    return {"payment_id": payment_id, "tenant_id": tenant_id, "amount": amount, "currency": currency}
