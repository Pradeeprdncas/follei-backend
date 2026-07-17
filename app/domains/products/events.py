"""Product domain events."""
def build_product_created_event(product_id: str, tenant_id: str, name: str, sku: str = None) -> dict:
    return {"product_id": product_id, "tenant_id": tenant_id, "name": name, "sku": sku}
