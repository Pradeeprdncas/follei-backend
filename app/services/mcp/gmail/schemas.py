"""Schemas for Gmail connector inputs and outputs."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class SendEmailInput(BaseModel):
    """Input parameters for sending a new email."""

    to: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Text or HTML content body")
    cc: Optional[List[EmailStr]] = Field(default=None, description="CC recipient list")
    bcc: Optional[List[EmailStr]] = Field(default=None, description="BCC recipient list")


class ReplyEmailInput(BaseModel):
    """Input parameters for replying to an existing thread."""

    thread_id: str = Field(..., description="Gmail Thread ID to reply to")
    body: str = Field(..., description="Body text of the reply")


class SearchEmailInput(BaseModel):
    """Input parameters for searching emails."""

    query: str = Field(..., description="Search query matching Gmail search format (e.g., 'from:boss label:unread')")
    max_results: int = Field(default=10, description="Max messages to fetch", ge=1, le=100)


class ReadThreadInput(BaseModel):
    """Input parameters for reading a complete email thread."""

    thread_id: str = Field(..., description="The Thread ID to fetch details for")


# JSON Schemas for tool registrations
SEND_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "format": "email", "description": "Recipient email address"},
        "subject": {"type": "string", "description": "Subject line"},
        "body": {"type": "string", "description": "Email body content"},
        "cc": {"type": "array", "items": {"type": "string", "format": "email"}, "description": "CC recipients"},
        "bcc": {"type": "array", "items": {"type": "string", "format": "email"}, "description": "BCC recipients"},
    },
    "required": ["to", "subject", "body"],
}

REPLY_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "thread_id": {"type": "string", "description": "Gmail Thread ID to reply to"},
        "body": {"type": "string", "description": "Body text of the reply"},
    },
    "required": ["thread_id", "body"],
}

SEARCH_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Gmail-style search query"},
        "max_results": {"type": "integer", "default": 10, "description": "Max results to return"},
    },
    "required": ["query"],
}

READ_THREAD_SCHEMA = {
    "type": "object",
    "properties": {
        "thread_id": {"type": "string", "description": "Gmail Thread ID to fetch"},
    },
    "required": ["thread_id"],
}
