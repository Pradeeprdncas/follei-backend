from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.tenancy import User
from app.services.knowledge.orchestrator import assemble_context

router = APIRouter(prefix="/knowledge/orchestrator", tags=["Knowledge Orchestrator"])

class ContextRequest(BaseModel):
    tenant_id: UUID
    query: str = Field(..., min_length=1, max_length=4000)
    lead_id: UUID | None = None
    customer_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=10)

@router.post("/context")
async def get_agent_context(payload: ContextRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return await assemble_context(db=db, tenant_id=str(payload.tenant_id), query=payload.query, lead_id=str(payload.lead_id) if payload.lead_id else None, customer_id=str(payload.customer_id) if payload.customer_id else None, top_k=payload.top_k)
