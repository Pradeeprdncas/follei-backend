"""One provenance-aware knowledge contract for every Follei worker."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.knowledge.contracts import AgentContextContract
from app.services.knowledge.orchestrator import build_agent_context

WORKER_TYPES = frozenset({
    "support", "sdr", "sales", "customer_success", "collections",
    "account_manager", "executive", "general",
})


async def build_worker_context(
    *,
    db: Session,
    worker_type: str,
    tenant_id: str,
    query: str,
    lead_id: str | None = None,
    customer_id: str | None = None,
    top_k: int = 5,
) -> dict:
    normalized = worker_type.strip().lower()
    if normalized not in WORKER_TYPES:
        raise ValueError(f"Unknown worker type: {worker_type}")
    context = await build_agent_context(
        db=db,
        tenant_id=tenant_id,
        query=query,
        lead_id=lead_id,
        customer_id=customer_id,
        top_k=top_k,
    )
    return AgentContextContract.model_validate(context).model_dump()
