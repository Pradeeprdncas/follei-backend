from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.schemas.conversation import (
    BuyingSignalRequest,
    BuyingSignalResponse,
    ConversationMetricsResponse,
    ConversationListResponse,
    ConversationParticipantRequest,
    ConversationResponse,
    CreateConversationRequest,
    EmotionRequest,
    EmotionResponse,
    IntentRequest,
    IntentResponse,
    ObjectionRequest,
    ObjectionResponse,
    ParticipantListResponse,
    ParticipantResponse,
    SentimentRequest,
    SentimentResponse,
    SummaryListResponse,
    SummaryRequest,
    SummaryResponse,
    UpdateConversationRequest,
)
from app.schemas.message import CreateMessageRequest, MessageListResponse, MessageResponse

router = APIRouter(prefix="/conversations", tags=["Conversations & Messages"])

CONVERSATIONS: dict[str, ConversationResponse] = {}
PARTICIPANTS: dict[str, ParticipantResponse] = {}
CONVERSATION_PARTICIPANTS: dict[str, list[str]] = {}
MESSAGES: dict[str, MessageResponse] = {}
CONVERSATION_MESSAGES: dict[str, list[str]] = {}
SUMMARIES: dict[str, SummaryResponse] = {}
CONVERSATION_SUMMARIES: dict[str, list[str]] = {}
INTENTS: dict[str, IntentResponse] = {}
SENTIMENTS: dict[str, SentimentResponse] = {}
EMOTIONS: dict[str, EmotionResponse] = {}
OBJECTIONS: dict[str, ObjectionResponse] = {}
BUYING_SIGNALS: dict[str, BuyingSignalResponse] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conversation_or_404(conversation_id: str) -> ConversationResponse:
    conversation = CONVERSATIONS.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def _conversation_with_counts(conversation: ConversationResponse) -> ConversationResponse:
    participants = [
        PARTICIPANTS[participant_id]
        for participant_id in CONVERSATION_PARTICIPANTS.get(conversation.id, [])
        if participant_id in PARTICIPANTS
    ]
    return conversation.model_copy(
        update={
            "participants": participants,
            "message_count": len(CONVERSATION_MESSAGES.get(conversation.id, [])),
        }
    )


def _check_optional_message(message_id: str | None) -> None:
    if message_id is not None and message_id not in MESSAGES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: CreateConversationRequest) -> ConversationResponse:
    now = _now()
    conversation_id = str(uuid4())
    conversation = ConversationResponse(
        id=conversation_id,
        title=payload.title,
        type=payload.type,
        status="active",
        tenant_id=payload.tenant_id,
        lead_id=payload.lead_id,
        customer_id=payload.customer_id,
        agent_id=payload.agent_id,
        channel=payload.channel,
        metadata=payload.metadata,
        participants=[],
        message_count=0,
        created_at=now,
        updated_at=now,
    )
    CONVERSATIONS[conversation_id] = conversation
    CONVERSATION_PARTICIPANTS[conversation_id] = []
    CONVERSATION_MESSAGES[conversation_id] = []
    return conversation


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    tenant_id: str | None = None,
    agent_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    items = [_conversation_with_counts(item) for item in CONVERSATIONS.values()]
    if tenant_id is not None:
        items = [item for item in items if item.tenant_id == tenant_id]
    if agent_id is not None:
        items = [item for item in items if item.agent_id == agent_id]
    if status_filter is not None:
        items = [item for item in items if item.status == status_filter]
    if type_filter is not None:
        items = [item for item in items if item.type == type_filter]

    total = len(items)
    start = (page - 1) * page_size
    return ConversationListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str) -> ConversationResponse:
    return _conversation_with_counts(_get_conversation_or_404(conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(conversation_id: str, payload: UpdateConversationRequest) -> ConversationResponse:
    conversation = _get_conversation_or_404(conversation_id)
    data = payload.model_dump(exclude_unset=True)
    updated = conversation.model_copy(update={**data, "updated_at": _now()})
    CONVERSATIONS[conversation_id] = updated
    return _conversation_with_counts(updated)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str) -> Response:
    _get_conversation_or_404(conversation_id)
    for participant_id in CONVERSATION_PARTICIPANTS.pop(conversation_id, []):
        PARTICIPANTS.pop(participant_id, None)
    for message_id in CONVERSATION_MESSAGES.pop(conversation_id, []):
        MESSAGES.pop(message_id, None)
    CONVERSATIONS.pop(conversation_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
def add_participant(conversation_id: str, payload: ConversationParticipantRequest) -> ParticipantResponse:
    _get_conversation_or_404(conversation_id)
    participant_id = str(uuid4())
    participant = ParticipantResponse(
        id=participant_id,
        conversation_id=conversation_id,
        user_id=payload.user_id,
        type=payload.type,
        role=payload.role,
        name=payload.name,
        metadata=payload.metadata,
        joined_at=_now(),
    )
    PARTICIPANTS[participant_id] = participant
    CONVERSATION_PARTICIPANTS.setdefault(conversation_id, []).append(participant_id)
    return participant


@router.get("/{conversation_id}/participants", response_model=ParticipantListResponse)
def list_participants(
    conversation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ParticipantListResponse:
    _get_conversation_or_404(conversation_id)
    items = [
        PARTICIPANTS[participant_id]
        for participant_id in CONVERSATION_PARTICIPANTS.get(conversation_id, [])
        if participant_id in PARTICIPANTS
    ]
    total = len(items)
    start = (page - 1) * page_size
    return ParticipantListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.delete("/{conversation_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_participant(conversation_id: str, participant_id: str) -> Response:
    _get_conversation_or_404(conversation_id)
    participant = PARTICIPANTS.get(participant_id)
    if participant is None or participant.conversation_id != conversation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    PARTICIPANTS.pop(participant_id, None)
    CONVERSATION_PARTICIPANTS[conversation_id] = [
        item_id for item_id in CONVERSATION_PARTICIPANTS.get(conversation_id, []) if item_id != participant_id
    ]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_message(conversation_id: str, payload: CreateMessageRequest) -> MessageResponse:
    _get_conversation_or_404(conversation_id)
    metadata = {**payload.metadata}
    metadata.setdefault("rag_used", bool(payload.citations or payload.tool_calls or payload.confidence is not None))
    message_id = str(uuid4())
    message = MessageResponse(
        id=message_id,
        conversation_id=conversation_id,
        content=payload.content,
        role=payload.role,
        user_id=payload.user_id,
        agent_id=payload.agent_id,
        citations=payload.citations,
        confidence=payload.confidence,
        tool_calls=payload.tool_calls,
        metadata=metadata,
        status="delivered",
        created_at=_now(),
    )
    MESSAGES[message_id] = message
    CONVERSATION_MESSAGES.setdefault(conversation_id, []).append(message_id)
    conversation = CONVERSATIONS[conversation_id]
    CONVERSATIONS[conversation_id] = conversation.model_copy(update={"updated_at": _now()})
    return message


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def list_conversation_messages(
    conversation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> MessageListResponse:
    _get_conversation_or_404(conversation_id)
    items = [
        MESSAGES[message_id]
        for message_id in CONVERSATION_MESSAGES.get(conversation_id, [])
        if message_id in MESSAGES
    ]
    total = len(items)
    start = (page - 1) * page_size
    return MessageListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.post("/{conversation_id}/summaries", response_model=SummaryResponse, status_code=status.HTTP_201_CREATED)
def create_summary(conversation_id: str, payload: SummaryRequest) -> SummaryResponse:
    conversation = _get_conversation_or_404(conversation_id)
    message_count = len(CONVERSATION_MESSAGES.get(conversation_id, []))
    summary_text = f"{conversation.title or 'Conversation'} summary with {message_count} messages."
    summary_id = str(uuid4())
    summary = SummaryResponse(
        id=summary_id,
        conversation_id=conversation_id,
        summary=summary_text[: payload.max_length],
        key_points=["Customer need captured", "Next step identified"],
        action_items=["Follow up with the customer"],
        sentiment="neutral",
        metadata={**payload.metadata, "focus": payload.focus},
        created_at=_now(),
    )
    SUMMARIES[summary_id] = summary
    CONVERSATION_SUMMARIES.setdefault(conversation_id, []).append(summary_id)
    return summary


@router.get("/{conversation_id}/summaries", response_model=SummaryListResponse)
def list_summaries(
    conversation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SummaryListResponse:
    _get_conversation_or_404(conversation_id)
    items = [SUMMARIES[item_id] for item_id in CONVERSATION_SUMMARIES.get(conversation_id, []) if item_id in SUMMARIES]
    total = len(items)
    start = (page - 1) * page_size
    return SummaryListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.get("/{conversation_id}/metrics", response_model=ConversationMetricsResponse)
def get_metrics(conversation_id: str) -> ConversationMetricsResponse:
    _get_conversation_or_404(conversation_id)
    from app.routers.message import MESSAGE_ATTACHMENTS, MESSAGE_REACTIONS

    message_ids = CONVERSATION_MESSAGES.get(conversation_id, [])
    messages = [MESSAGES[item_id] for item_id in message_ids if item_id in MESSAGES]
    confidences = [message.confidence for message in messages if message.confidence is not None]
    return ConversationMetricsResponse(
        conversation_id=conversation_id,
        message_count=len(messages),
        participant_count=len(CONVERSATION_PARTICIPANTS.get(conversation_id, [])),
        user_message_count=len([message for message in messages if message.role == "user"]),
        assistant_message_count=len([message for message in messages if message.role == "assistant"]),
        attachment_count=sum(len(MESSAGE_ATTACHMENTS.get(message_id, [])) for message_id in message_ids),
        reaction_count=sum(len(MESSAGE_REACTIONS.get(message_id, [])) for message_id in message_ids),
        summary_count=len(CONVERSATION_SUMMARIES.get(conversation_id, [])),
        avg_confidence=round(sum(confidences) / len(confidences), 2) if confidences else None,
        rag_used_count=len([message for message in messages if message.metadata.get("rag_used")]),
        updated_at=_now(),
    )


@router.post("/{conversation_id}/intents", response_model=IntentResponse, status_code=status.HTTP_201_CREATED)
def create_intent(conversation_id: str, payload: IntentRequest) -> IntentResponse:
    _get_conversation_or_404(conversation_id)
    _check_optional_message(payload.message_id)
    item_id = str(uuid4())
    item = IntentResponse(id=item_id, conversation_id=conversation_id, created_at=_now(), **payload.model_dump())
    INTENTS[item_id] = item
    return item


@router.post("/{conversation_id}/sentiments", response_model=SentimentResponse, status_code=status.HTTP_201_CREATED)
def create_sentiment(conversation_id: str, payload: SentimentRequest) -> SentimentResponse:
    _get_conversation_or_404(conversation_id)
    _check_optional_message(payload.message_id)
    item_id = str(uuid4())
    item = SentimentResponse(id=item_id, conversation_id=conversation_id, created_at=_now(), **payload.model_dump())
    SENTIMENTS[item_id] = item
    return item


@router.post("/{conversation_id}/emotions", response_model=EmotionResponse, status_code=status.HTTP_201_CREATED)
def create_emotion(conversation_id: str, payload: EmotionRequest) -> EmotionResponse:
    _get_conversation_or_404(conversation_id)
    _check_optional_message(payload.message_id)
    item_id = str(uuid4())
    item = EmotionResponse(id=item_id, conversation_id=conversation_id, created_at=_now(), **payload.model_dump())
    EMOTIONS[item_id] = item
    return item


@router.post("/{conversation_id}/objections", response_model=ObjectionResponse, status_code=status.HTTP_201_CREATED)
def create_objection(conversation_id: str, payload: ObjectionRequest) -> ObjectionResponse:
    _get_conversation_or_404(conversation_id)
    _check_optional_message(payload.message_id)
    item_id = str(uuid4())
    item = ObjectionResponse(id=item_id, conversation_id=conversation_id, created_at=_now(), **payload.model_dump())
    OBJECTIONS[item_id] = item
    return item


@router.post("/{conversation_id}/buying-signals", response_model=BuyingSignalResponse, status_code=status.HTTP_201_CREATED)
def create_buying_signal(conversation_id: str, payload: BuyingSignalRequest) -> BuyingSignalResponse:
    _get_conversation_or_404(conversation_id)
    _check_optional_message(payload.message_id)
    item_id = str(uuid4())
    item = BuyingSignalResponse(id=item_id, conversation_id=conversation_id, created_at=_now(), **payload.model_dump())
    BUYING_SIGNALS[item_id] = item
    return item
