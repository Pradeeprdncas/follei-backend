from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.domains.messaging.service import MessagingService
from app.domains.messaging.repository import MessagingRepository
from app.domains.messaging.schemas import (
    MessageSendRequest,
    MessageResponse,
    MessageListResponse,
    HealthResponse,
)
from app.domains.messaging.exceptions import MessageValidationError, MessageNotFoundError, ProviderNotConfigured
from app.domains.messaging.dispatcher import MessageDispatcher

router = APIRouter(prefix="/messaging", tags=["Messaging"])


def get_service(db: Session = Depends(get_db)) -> MessagingService:
    repo = MessagingRepository(db)
    dispatcher = MessageDispatcher()
    return MessagingService(repo, dispatcher)


@router.post("/send", response_model=MessageResponse, status_code=201)
async def send_message(
    body: MessageSendRequest,
    service: MessagingService = Depends(get_service),
):
    """Send a message via the specified channel (email, whatsapp, sms)."""
    try:
        return await service.send_message(body)
    except MessageValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ProviderNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/messages/{message_id}", response_model=MessageResponse)
def get_message(
    message_id: str,
    service: MessagingService = Depends(get_service),
):
    """Get a message by ID or public ID."""
    try:
        return service.get_message(message_id)
    except MessageNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/messages", response_model=MessageListResponse)
def list_messages(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: MessagingService = Depends(get_service),
):
    """List messages, optionally filtered by tenant."""
    items = service.list_messages(tenant_id=tenant_id, limit=limit, offset=offset)
    return MessageListResponse(items=items, total=len(items))


@router.get("/health", response_model=HealthResponse)
def health_check(
    service: MessagingService = Depends(get_service),
):
    """Health check for messaging providers."""
    return service.get_health()
