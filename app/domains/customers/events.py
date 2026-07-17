"""Customer domain events."""
def build_customer_created_event(customer_id: str, tenant_id: str, name: str) -> dict:
    return {"customer_id": customer_id, "tenant_id": tenant_id, "name": name}


def build_customer_health_changed_event(customer_id: str, tenant_id: str, health_score: int, churn_risk: str) -> dict:
    return {"customer_id": customer_id, "tenant_id": tenant_id, "health_score": health_score, "churn_risk": churn_risk}
