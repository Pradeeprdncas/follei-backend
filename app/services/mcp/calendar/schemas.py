"""Schemas for Calendar connector tools."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class CalendarCreateEventInput(BaseModel):
    """Input parameters to create a calendar event."""

    provider: str = Field(..., description="Calendar provider ('google' or 'outlook')")
    subject: str = Field(..., description="Event subject or title")
    body: str = Field(..., description="Event description body")
    start_time: str = Field(..., description="ISO 8601 start date-time string")
    end_time: str = Field(..., description="ISO 8601 end date-time string")
    time_zone: str = Field(default="UTC", description="Target timezone")
    attendees: Optional[List[EmailStr]] = Field(default=None, description="Attendee email addresses")


class CalendarUpdateEventInput(BaseModel):
    """Input parameters to update an existing event."""

    provider: str = Field(..., description="Calendar provider ('google' or 'outlook')")
    event_id: str = Field(..., description="Unique provider event ID")
    event_data: Dict[str, Any] = Field(..., description="Key-value fields to update (e.g. subject, start_time)")


class CalendarCancelEventInput(BaseModel):
    """Input parameters to cancel/delete a calendar event."""

    provider: str = Field(..., description="Calendar provider ('google' or 'outlook')")
    event_id: str = Field(..., description="Event ID to cancel")


class CalendarGetAvailabilityInput(BaseModel):
    """Input parameters to query free-busy availability schedules."""

    provider: str = Field(..., description="Calendar provider ('google' or 'outlook')")
    start_time: str = Field(..., description="ISO 8601 start time range limit")
    end_time: str = Field(..., description="ISO 8601 end time range limit")
    emails: List[EmailStr] = Field(..., description="List of email addresses to query schedules for")
    time_zone: str = Field(default="UTC")


# JSON Schemas
CALENDAR_CREATE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": ["google", "outlook"]},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"},
        "time_zone": {"type": "string", "default": "UTC"},
        "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
    },
    "required": ["provider", "subject", "body", "start_time", "end_time"],
}

CALENDAR_UPDATE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": ["google", "outlook"]},
        "event_id": {"type": "string"},
        "event_data": {"type": "object"},
    },
    "required": ["provider", "event_id", "event_data"],
}

CALENDAR_CANCEL_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": ["google", "outlook"]},
        "event_id": {"type": "string"},
    },
    "required": ["provider", "event_id"],
}

CALENDAR_GET_AVAILABILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": ["google", "outlook"]},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"},
        "emails": {"type": "array", "items": {"type": "string", "format": "email"}},
        "time_zone": {"type": "string", "default": "UTC"},
    },
    "required": ["provider", "start_time", "end_time", "emails"],
}
