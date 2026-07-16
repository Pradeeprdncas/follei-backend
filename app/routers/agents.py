import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Any

try:
    import anthropic
except ImportError:
    anthropic = None

from app import schema
from app.database.session import get_db
from app.models.agents.agent import Agent
from app.models.tenancy import User
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/agents",
    tags=["AI Agents"]
)

# Initialize the Anthropic client (using ANTHROPIC_API_KEY from environment)
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = (
    anthropic.Anthropic(api_key=anthropic_api_key)
    if anthropic is not None and anthropic_api_key
    else None
)

@router.post("", response_model=schema.Agent, status_code=status.HTTP_201_CREATED)
def create_agent(
    agent_in: schema.AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Create a new AI worker (e.g., "SDR Agent").
    """
    new_agent = Agent(
        tenant_id=current_user.tenant_id,
        name=agent_in.name,
        role=agent_in.role,
        system_prompt=agent_in.system_prompt,
        tools=agent_in.tools
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent

@router.get("", response_model=List[schema.Agent])
def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    List active agents.
    """
    agents = db.query(Agent).filter(Agent.tenant_id == current_user.tenant_id).all()
    return agents

@router.post("/{agent_id}/chat", response_model=schema.AIChatResponse)
def chat_with_agent(
    agent_id: uuid.UUID,
    chat_request: schema.AIChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Chat with a specific AI agent using the Claude API.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == current_user.tenant_id
    ).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found or unauthorized")
    
    if anthropic is None:
        raise HTTPException(status_code=503, detail="Anthropic package is not installed.")

    if anthropic_client is None:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not configured.")

    try:
        # Use the agent's system prompt and the user's message to interact with Claude
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620", # You can choose other Claude models here
            max_tokens=1024,
            system=agent.system_prompt,
            messages=[
                {"role": "user", "content": chat_request.message}
            ]
        )
        # Assuming the response structure, extract the text content
        return {"response": response.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Claude API: {e}")
