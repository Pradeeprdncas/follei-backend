from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.routers.conversation import CONVERSATION_MESSAGES, MESSAGES
from app.schemas.message import (
    AttachmentListResponse,
    AttachmentRequest,
    AttachmentResponse,
    MessageResponse,
    ReactionRequest,
    ReactionResponse,
    UpdateMessageRequest,
)

router = APIRouter(prefix="/messages", tags=["Conversations & Messages"])

ATTACHMENTS: dict[str, AttachmentResponse] = {}
MESSAGE_ATTACHMENTS: dict[str, list[str]] = {}
REACTIONS: dict[str, ReactionResponse] = {}
MESSAGE_REACTIONS: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_message_or_404(message_id: str) -> MessageResponse:
    message = MESSAGES.get(message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message


@router.get("/{message_id}", response_model=MessageResponse)
def get_message(message_id: str) -> MessageResponse:
    return _get_message_or_404(message_id)


@router.patch("/{message_id}", response_model=MessageResponse)
def update_message(message_id: str, payload: UpdateMessageRequest) -> MessageResponse:
    message = _get_message_or_404(message_id)
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data and data["metadata"] is not None:
        data["metadata"] = {**message.metadata, **data["metadata"]}
    updated = message.model_copy(update=data)
    MESSAGES[message_id] = updated
    return updated


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: str) -> Response:
    message = _get_message_or_404(message_id)
    message_ids = CONVERSATION_MESSAGES.get(message.conversation_id, [])
    CONVERSATION_MESSAGES[message.conversation_id] = [item_id for item_id in message_ids if item_id != message_id]
    for attachment_id in MESSAGE_ATTACHMENTS.pop(message_id, []):
        ATTACHMENTS.pop(attachment_id, None)
    for reaction_id in MESSAGE_REACTIONS.pop(message_id, []):
        REACTIONS.pop(reaction_id, None)
    MESSAGES.pop(message_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{message_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
def create_attachment(message_id: str, payload: AttachmentRequest) -> AttachmentResponse:
    _get_message_or_404(message_id)
    attachment_id = str(uuid4())
    attachment = AttachmentResponse(
        id=attachment_id,
        message_id=message_id,
        filename=payload.filename,
        url=payload.url,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        caption=payload.caption,
        metadata=payload.metadata,
        created_at=_now(),
    )
    ATTACHMENTS[attachment_id] = attachment
    MESSAGE_ATTACHMENTS.setdefault(message_id, []).append(attachment_id)
    return attachment


@router.get("/{message_id}/attachments", response_model=AttachmentListResponse)
def list_attachments(
    message_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AttachmentListResponse:
    _get_message_or_404(message_id)
    items = [ATTACHMENTS[item_id] for item_id in MESSAGE_ATTACHMENTS.get(message_id, []) if item_id in ATTACHMENTS]
    total = len(items)
    start = (page - 1) * page_size
    return AttachmentListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.post("/{message_id}/reactions", response_model=ReactionResponse, status_code=status.HTTP_201_CREATED)
def create_reaction(message_id: str, payload: ReactionRequest) -> ReactionResponse:
    _get_message_or_404(message_id)
    reaction_id = str(uuid4())
    reaction = ReactionResponse(
        id=reaction_id,
        message_id=message_id,
        emoji=payload.emoji,
        user_id=payload.user_id,
        metadata=payload.metadata,
        created_at=_now(),
    )
    REACTIONS[reaction_id] = reaction
    MESSAGE_REACTIONS.setdefault(message_id, []).append(reaction_id)
    return reaction
