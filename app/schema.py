"""Shared Pydantic schemas."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List


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

class RegisterRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    admin_email: EmailStr
    admin_password: str
    admin_first_name: str = "Admin"
    admin_last_name: str = "User"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool = True
    created_at: datetime

class AgentCreate(BaseModel):
    name: str
    role: str
    system_prompt: str
    tenant_id: Optional[UUID] = None
    tools: List[str] = []

class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    role: str
    system_prompt: str
    tools: List[str] = []
    created_at: datetime

class AIChatRequest(BaseModel):
    message: str

class AIChatResponse(BaseModel):
    response: str


