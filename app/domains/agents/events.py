"""Agent domain events."""
def build_agent_created_event(agent_id: str, tenant_id: str, name: str, role: str) -> dict:
    return {"agent_id": agent_id, "tenant_id": tenant_id, "name": name, "role": role}


def build_agent_task_assigned_event(task_id: str, agent_id: str, tenant_id: str, task_type: str) -> dict:
    return {"task_id": task_id, "agent_id": agent_id, "tenant_id": tenant_id, "task_type": task_type}
