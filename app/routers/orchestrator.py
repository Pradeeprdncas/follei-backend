from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.knowledge.orchestrator import build_agent_context

router = APIRouter(prefix="/knowledge/orchestrator", tags=["knowledge-orchestrator"])
class AgentContextRequest(BaseModel):
    tenant_id: str
    query: str = Field(..., min_length=1, max_length=4000)
    lead_id: str | None = None
    customer_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)

@router.post("/context")
async def agent_context(payload: AgentContextRequest, db: Session = Depends(get_db)):
    return await build_agent_context(db=db, tenant_id=payload.tenant_id, query=payload.query, lead_id=payload.lead_id, customer_id=payload.customer_id, top_k=payload.top_k)
