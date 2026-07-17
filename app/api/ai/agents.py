import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Any

from app import schema
from app.database.session import get_db
from app.models.agents.agent import Agent
from app.models.tenancy import User
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/agents", tags=["AI Agents"])


@router.post("", response_model=schema.Agent, status_code=status.HTTP_201_CREATED)
def create_agent(
    agent_in: schema.AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    new_agent = Agent(
        tenant_id=current_user.tenant_id,
        name=agent_in.name,
        role=agent_in.role,
        system_prompt=agent_in.system_prompt,
        tools=agent_in.tools,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent


@router.get("", response_model=List[schema.Agent])
def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    agents = db.query(Agent).filter(Agent.tenant_id == current_user.tenant_id).all()
    return agents


@router.post("/{agent_id}/chat", response_model=schema.AIChatResponse)
def chat_with_agent(
    agent_id: uuid.UUID,
    chat_request: schema.AIChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    raise HTTPException(status_code=501, detail="Cloud AI (Anthropic) is disabled. Use local AI endpoints instead.")
