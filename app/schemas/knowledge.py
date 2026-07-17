"""Knowledge Base Schemas - Pydantic models for knowledge API."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    """Request to create knowledge base item."""
    title: str = Field(examples=["Company FAQ"])
    description: Optional[str] = Field(default=None, examples=["Frequently asked questions"])
    file_type: str = Field(examples=["pdf"])
    file_path: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None, examples=["https://example.com/faq"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response."""
    id: str
    title: str
    description: Optional[str] = None
    file_type: str
    file_path: Optional[str] = None
    url: Optional[str] = None
    status: str
    chunk_count: int
    metadata: Optional[Dict[str, Any]] = None
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """List of knowledge base items."""
    items: List[KnowledgeBaseResponse]
    total: int
    page: int
    page_size: int


class RAGChatRequest(BaseModel):
    """RAG chat request."""
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    message: str = Field(examples=["What are your business hours?"])
    conversation_id: Optional[str] = Field(default=None, examples=["22222222-2222-4222-8222-222222222222"])
    lead_id: Optional[str] = Field(default=None, examples=["33333333-3333-4333-8333-333333333333"])


class RAGChatResponse(BaseModel):
    """RAG chat response."""
    answer: str
    sources: List[str]
    intent: str
    confidence: float
    conversation_id: str
    message_id: str
    timestamp: datetime