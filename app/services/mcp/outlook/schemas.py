"""Schemas for Outlook connector inputs and outputs."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class OutlookSendEmailInput(BaseModel):
    """Input parameters for sending a Microsoft Graph email."""

    to: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Body content of the email")
    cc: Optional[List[EmailStr]] = Field(default=None, description="List of CC recipient emails")
    bcc: Optional[List[EmailStr]] = Field(default=None, description="List of BCC recipient emails")


class OutlookReplyEmailInput(BaseModel):
    """Input parameters for replying to an Outlook message."""

    message_id: str = Field(..., description="The Microsoft Graph message ID to reply to")
    body: str = Field(..., description="Body of the reply message")


class OutlookReadEmailInput(BaseModel):
    """Input parameters for reading a specific Outlook message."""

    message_id: str = Field(..., description="Message ID to fetch details for")


class OutlookCreateEventInput(BaseModel):
    """Input parameters for creating an Outlook calendar event."""

    subject: str = Field(..., description="Subject of the event")
    body: str = Field(..., description="Description details of the event")
    start_time: str = Field(..., description="ISO 8601 start time (e.g. '2026-06-15T19:00:00')")
    end_time: str = Field(..., description="ISO 8601 end time (e.g. '2026-06-15T20:00:00')")
    time_zone: str = Field(default="UTC", description="Timezone name (e.g. 'Pacific Standard Time', 'UTC')")
    attendees: Optional[List[EmailStr]] = Field(default=None, description="List of attendee email addresses")


# JSON Schemas
OUTLOOK_SEND_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "format": "email", "description": "Recipient email address"},
        "subject": {"type": "string", "description": "Email subject line"},
        "body": {"type": "string", "description": "Email body content"},
        "cc": {"type": "array", "items": {"type": "string", "format": "email"}},
        "bcc": {"type": "array", "items": {"type": "string", "format": "email"}},
    },
    "required": ["to", "subject", "body"],
}

OUTLOOK_REPLY_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "message_id": {"type": "string", "description": "MS Graph Message ID to reply to"},
        "body": {"type": "string", "description": "Reply content body"},
    },
    "required": ["message_id", "body"],
}

OUTLOOK_READ_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "message_id": {"type": "string", "description": "MS Graph Message ID to read"},
    },
    "required": ["message_id"],
}

OUTLOOK_CREATE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "Event subject"},
        "body": {"type": "string", "description": "Event description text"},
        "start_time": {"type": "string", "description": "ISO start datetime string"},
        "end_time": {"type": "string", "description": "ISO end datetime string"},
        "time_zone": {"type": "string", "default": "UTC"},
        "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
    },
    "required": ["subject", "body", "start_time", "end_time"],
}
