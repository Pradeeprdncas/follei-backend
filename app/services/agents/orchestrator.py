"""Worker orchestration: a shared knowledge contract plus turn dispatch.

Two responsibilities:
  * build_worker_context() — the pre-existing provenance-aware knowledge
    contract every worker can draw on.
  * run_worker() — dispatch one conversation turn to the right worker
    implementation (support / sdr / sales today) and, for SDR, auto-hand off to
    Sales once the lead crosses the qualification threshold. This is what makes
    "speak, and the right worker replies" real for the voice loop and any other
    caller, instead of every entry point wiring workers up by hand.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.knowledge.contracts import AgentContextContract
from app.services.knowledge.orchestrator import build_agent_context

WORKER_TYPES = frozenset({
    "support", "sdr", "sales", "customer_success", "collections",
    "account_manager", "executive", "general",
})

# Worker types run_worker() can actually dispatch a turn to today. The rest of
# WORKER_TYPES are valid context targets but have no turn handler yet.
DISPATCHABLE_WORKER_TYPES = frozenset({"support", "sdr", "sales"})


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


async def run_worker(
    db: Session,
    *,
    worker_type: str,
    tenant_id: str,
    text: str,
    lead_id: str | None = None,
    session_id: str | None = None,
    channel: str = "voice",
    response_language: str | None = None,
) -> dict[str, Any]:
    """Dispatch one turn to a worker; auto-hand SDR->Sales on qualification.

    Returns the chosen worker's result dict (see each worker module). When an
    SDR turn qualifies the lead, the Sales worker runs on the same turn and its
    result is returned instead, tagged with handed_off_from="sdr" plus the SDR
    result under sdr_result — so the caller (e.g. the voice loop) speaks the
    Sales reply without needing to know a handoff happened.
    """
    normalized = worker_type.strip().lower()
    if normalized not in DISPATCHABLE_WORKER_TYPES:
        raise ValueError(
            f"Worker type {worker_type!r} is not dispatchable. "
            f"Dispatchable: {sorted(DISPATCHABLE_WORKER_TYPES)}"
        )

    if normalized == "support":
        from app.services.agents.support.worker import handle_inbound_message
        return await handle_inbound_message(
            db, tenant_id=tenant_id, text=text, session_id=session_id, channel=channel,
            response_language=response_language,
        )

    if normalized == "sales":
        from app.services.agents.sales.worker import handle_sales_turn
        return await handle_sales_turn(
            db, tenant_id=tenant_id, text=text, lead_id=lead_id,
            session_id=session_id, channel=channel, response_language=response_language,
        )

    # normalized == "sdr"
    from app.services.agents.sdr.worker import handle_sdr_turn
    sdr_result = await handle_sdr_turn(
        db, tenant_id=tenant_id, text=text, lead_id=lead_id,
        session_id=session_id, channel=channel, response_language=response_language,
    )
    if not sdr_result.get("handoff_to_sales"):
        return sdr_result

    # Stage-gated handoff: the lead just crossed the qualification threshold, so
    # progress the same turn with the Sales worker and surface its reply.
    from app.services.agents.sales.worker import handle_sales_turn
    sales_result = await handle_sales_turn(
        db, tenant_id=tenant_id, text=text, lead_id=lead_id,
        session_id=session_id, channel=channel, response_language=response_language,
    )
    sales_result["handed_off_from"] = "sdr"
    sales_result["sdr_result"] = sdr_result
    return sales_result
