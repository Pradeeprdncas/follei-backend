"""Schemas for WhatsApp connector tools."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WhatsAppSendMessageInput(BaseModel):
    """Parameters to send a plain text message via WhatsApp Business API."""

    to: str = Field(..., description="Recipient phone number with country code (e.g. '+14155552671')")
    body: str = Field(..., description="Message text content")


class WhatsAppSendTemplateInput(BaseModel):
    """Parameters to send a template message."""

    to: str = Field(..., description="Recipient phone number with country code")
    template_name: str = Field(..., description="Name of the pre-approved WhatsApp message template")
    language_code: str = Field(default="en_US", description="Language code matching the template registration")
    components: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Dynamic parameters for the template placeholders"
    )


class WhatsAppSendMediaInput(BaseModel):
    """Parameters to send media files (image, document, audio, video)."""

    to: str = Field(..., description="Recipient phone number with country code")
    media_type: str = Field(..., description="Type of media ('image', 'document', 'audio', 'video')")
    media_url: str = Field(..., description="Publicly accessible URL of the media asset")
    caption: Optional[str] = Field(default=None, description="Optional caption to overlay on the media (images/videos only)")


class WhatsAppGetConversationInput(BaseModel):
    """Parameters to retrieve conversation details/logs."""

    phone_number: str = Field(..., description="User's phone number to query history for")
    limit: int = Field(default=10, description="Max messages to fetch", ge=1, le=100)


# JSON Schemas
WHATSAPP_SEND_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["to", "body"],
}

WHATSAPP_SEND_TEMPLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "template_name": {"type": "string"},
        "language_code": {"type": "string", "default": "en_US"},
        "components": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["to", "template_name"],
}

WHATSAPP_SEND_MEDIA_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "media_type": {"type": "string", "enum": ["image", "document", "audio", "video"]},
        "media_url": {"type": "string", "format": "uri"},
        "caption": {"type": "string"},
    },
    "required": ["to", "media_type", "media_url"],
}

WHATSAPP_GET_CONVERSATION_SCHEMA = {
    "type": "object",
    "properties": {
        "phone_number": {"type": "string"},
        "limit": {"type": "integer", "default": 10},
    },
    "required": ["phone_number"],
}
