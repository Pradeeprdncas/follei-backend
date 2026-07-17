"""Integration domain events."""
def build_integration_connected_event(connection_id: str, tenant_id: str, integration_name: str) -> dict:
    return {"connection_id": connection_id, "tenant_id": tenant_id, "integration_name": integration_name}


def build_integration_disconnected_event(connection_id: str, tenant_id: str, integration_name: str) -> dict:
    return {"connection_id": connection_id, "tenant_id": tenant_id, "integration_name": integration_name}
