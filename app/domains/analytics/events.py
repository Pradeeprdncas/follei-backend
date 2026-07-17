"""Analytics domain events."""
def build_metric_recorded_event(tenant_id: str, metric_name: str, metric_value: float, metric_date: str) -> dict:
    return {"tenant_id": tenant_id, "metric_name": metric_name, "metric_value": metric_value, "metric_date": metric_date}
