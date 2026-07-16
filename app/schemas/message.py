from typing import Any

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    content: str = Field(examples=["Here is the answer based on your knowledge base."])
    role: str = Field(default="user", examples=["assistant"])
    user_id: str | None = Field(default=None, examples=["55555555-5555-4555-8555-555555555555"])
    agent_id: str | None = Field(default=None, examples=["44444444-4444-4444-8444-444444444444"])
    citations: list[dict[str, Any]] = Field(
        default_factory=list,
        examples=[[{"source": "pricing-guide", "url": "https://example.com/pricing", "snippet": "Plan starts at $99"}]],
    )
    confidence: float | None = Field(default=None, examples=[0.91])
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        examples=[[{"name": "search_knowledge_base", "status": "success"}]],
    )
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"rag_used": True}])


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    content: str
    role: str
    user_id: str | None = None
    agent_id: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: str


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int


class UpdateMessageRequest(BaseModel):
    content: str | None = Field(default=None, examples=["Updated answer text"])
    status: str | None = Field(default=None, examples=["edited"])
    metadata: dict[str, Any] | None = Field(default=None, examples=[{"edited_by": "agent"}])


class AttachmentRequest(BaseModel):
    filename: str = Field(examples=["pricing.pdf"])
    url: str = Field(examples=["https://example.com/files/pricing.pdf"])
    mime_type: str | None = Field(default=None, examples=["application/pdf"])
    size_bytes: int | None = Field(default=None, examples=[204800])
    caption: str | None = Field(default=None, examples=["Pricing document"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"source": "upload"}])


class AttachmentResponse(BaseModel):
    id: str
    message_id: str
    filename: str
    url: str
    mime_type: str | None = None
    size_bytes: int | None = None
    caption: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AttachmentListResponse(BaseModel):
    items: list[AttachmentResponse]
    total: int
    page: int
    page_size: int


class ReactionRequest(BaseModel):
    emoji: str = Field(examples=["like"])
    user_id: str | None = Field(default=None, examples=["55555555-5555-4555-8555-555555555555"])
    metadata: dict[str, Any] = Field(default_factory=dict, examples=[{"source": "swagger"}])


class ReactionResponse(BaseModel):
    id: str
    message_id: str
    emoji: str
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
