from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.agents.orchestrator import build_worker_context
from app.core.security import get_authenticated_tenant_id, require_matching_tenant

router = APIRouter(prefix="/knowledge/orchestrator", tags=["knowledge-orchestrator"])
class AgentContextRequest(BaseModel):
    tenant_id: str
    query: str = Field(..., min_length=1, max_length=4000)
    lead_id: str | None = None
    customer_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    worker_type: Literal["support", "sdr", "sales", "customer_success", "collections", "account_manager", "executive", "general"] = "general"

@router.post("/context")
async def agent_context(
    payload: AgentContextRequest,
    db: Session = Depends(get_db),
    authenticated_tenant_id: str = Depends(get_authenticated_tenant_id),
):
    require_matching_tenant(payload.tenant_id, authenticated_tenant_id)
    return await build_worker_context(db=db, worker_type=payload.worker_type, tenant_id=payload.tenant_id, query=payload.query, lead_id=payload.lead_id, customer_id=payload.customer_id, top_k=payload.top_k)
