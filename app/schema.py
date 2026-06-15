"""Shared Pydantic schemas."""
from pydantic import BaseModel
from typing import Optional


class DocumentUploadResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    status: str
    message: str


class ChatRequest(BaseModel):
    question: str
    tenant_id: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict]
    confidence: float
    supported: bool
    reason: str
