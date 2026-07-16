from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, examples=["Website pricing question"])
    type: str = Field(default="sales", examples=["sales"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    lead_id: str | None = Field(default=None, examples=["22222222-2222-4222-8222-222222222222"])
    customer_id: str | None = Field(default=None, examples=["33333333-3333-4333-8333-333333333333"])
    agent_id: str | None = Field(default=None, examples=["44444444-4444-4444-8444-444444444444"])
    channel: str = Field(default="web", examples=["web"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"source": "swagger"}])


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, examples=["Updated pricing question"])
    type: str | None = Field(default=None, examples=["support"])
    status: str | None = Field(default=None, examples=["active"])
    lead_id: str | None = Field(default=None, examples=["22222222-2222-4222-8222-222222222222"])
    customer_id: str | None = Field(default=None, examples=["33333333-3333-4333-8333-333333333333"])
    agent_id: str | None = Field(default=None, examples=["44444444-4444-4444-8444-444444444444"])
    channel: str | None = Field(default=None, examples=["email"])
    metadata: dict[str, Any] | None = Field(default=None, examples=[{"priority": "high"}])


class ConversationParticipantRequest(BaseModel):
    user_id: str | None = Field(default=None, examples=["55555555-5555-4555-8555-555555555555"])
    type: str = Field(examples=["lead"])
    role: str | None = Field(default=None, examples=["buyer"])
    name: str | None = Field(default=None, examples=["Asha Kumar"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"timezone": "Asia/Kolkata"}])


class ParticipantResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: str | None = None
    type: str
    role: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    joined_at: str


class ConversationResponse(BaseModel):
    id: str
    title: str | None = None
    type: str
    status: str
    tenant_id: str
    lead_id: str | None = None
    customer_id: str | None = None
    agent_id: str | None = None
    channel: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    participants: list[ParticipantResponse] = Field(default_factory=list)
    message_count: int = 0
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class ParticipantListResponse(BaseModel):
    items: list[ParticipantResponse]
    total: int
    page: int
    page_size: int


class SummaryRequest(BaseModel):
    max_length: int = Field(default=200, examples=[200])
    focus: str | None = Field(default=None, examples=["sales next steps"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"generated_by": "ai"}])


class SummaryResponse(BaseModel):
    id: str
    conversation_id: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    sentiment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SummaryListResponse(BaseModel):
    items: list[SummaryResponse]
    total: int
    page: int
    page_size: int


class ConversationMetricsResponse(BaseModel):
    conversation_id: str
    message_count: int
    participant_count: int
    user_message_count: int
    assistant_message_count: int
    attachment_count: int
    reaction_count: int
    summary_count: int
    avg_confidence: float | None = None
    rag_used_count: int
    updated_at: str


class IntentRequest(BaseModel):
    message_id: str | None = Field(default=None, examples=["88888888-8888-4888-8888-888888888888"])
    intent: str = Field(examples=["pricing_question"])
    confidence: float | None = Field(default=None, examples=[0.87])
    entities: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"type": "plan", "value": "pro"}]])
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    intent: str
    confidence: float | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SentimentRequest(BaseModel):
    message_id: str | None = Field(default=None, examples=["88888888-8888-4888-8888-888888888888"])
    sentiment: str = Field(examples=["positive"])
    score: float | None = Field(default=None, examples=[0.76])
    aspects: list[dict[str, Any]] = Field(default_factory=list, examples=[[{"topic": "pricing", "sentiment": "neutral"}]])
    metadata: dict[str, Any] = Field(default_factory=dict)


class SentimentResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    sentiment: str
    score: float | None = None
    aspects: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class EmotionRequest(BaseModel):
    message_id: str | None = Field(default=None, examples=["88888888-8888-4888-8888-888888888888"])
    emotion: str = Field(examples=["curious"])
    intensity: float | None = Field(default=None, examples=[0.64])
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmotionResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    emotion: str
    intensity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ObjectionRequest(BaseModel):
    message_id: str | None = Field(default=None, examples=["88888888-8888-4888-8888-888888888888"])
    objection_type: str = Field(examples=["price"])
    description: str | None = Field(default=None, examples=["Customer thinks the plan is expensive"])
    severity: str | None = Field(default=None, examples=["medium"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectionResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    objection_type: str
    description: str | None = None
    severity: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class BuyingSignalRequest(BaseModel):
    message_id: str | None = Field(default=None, examples=["88888888-8888-4888-8888-888888888888"])
    signal_type: str = Field(examples=["demo_requested"])
    description: str | None = Field(default=None, examples=["Customer asked for a product demo"])
    strength: float | None = Field(default=None, examples=[0.9])
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyingSignalResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    signal_type: str
    description: str | None = None
    strength: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
