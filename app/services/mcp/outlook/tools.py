"""Outlook MCP tools implementation."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.outlook.service import OutlookService
from mcp.outlook.schemas import (
    OUTLOOK_SEND_EMAIL_SCHEMA,
    OUTLOOK_REPLY_EMAIL_SCHEMA,
    OUTLOOK_READ_EMAIL_SCHEMA,
    OUTLOOK_CREATE_EVENT_SCHEMA,
)


class OutlookSendEmailTool(MCPTool):
    """Tool to send a new email via Outlook."""

    def __init__(self, service: OutlookService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "outlook_send_email"

    @property
    def description(self) -> str:
        return "Sends an email message using MS Graph Outlook."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return OUTLOOK_SEND_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"status": {"type": "string"}}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_email(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc"),
                bcc=params.get("bcc"),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class OutlookReplyEmailTool(MCPTool):
    """Tool to reply to an Outlook email message."""

    def __init__(self, service: OutlookService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "outlook_reply_email"

    @property
    def description(self) -> str:
        return "Replies to a specific Outlook email message."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return OUTLOOK_REPLY_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"draft_id": {"type": "string"}}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.reply_email(
                message_id=params["message_id"],
                body=params["body"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class OutlookReadEmailTool(MCPTool):
    """Tool to read a single Outlook email."""

    def __init__(self, service: OutlookService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "outlook_read_email"

    @property
    def description(self) -> str:
        return "Retrieves the contents and subject of a specific Outlook email."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return OUTLOOK_READ_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.read_email(message_id=params["message_id"])
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class OutlookCreateEventTool(MCPTool):
    """Tool to create an event on Outlook Calendar."""

    def __init__(self, service: OutlookService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "outlook_create_event"

    @property
    def description(self) -> str:
        return "Creates a new calendar event on Microsoft Graph Outlook Calendar."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CALENDAR

    @property
    def input_schema(self) -> Dict[str, Any]:
        return OUTLOOK_CREATE_EVENT_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_event(
                subject=params["subject"],
                body=params["body"],
                start_time=params["start_time"],
                end_time=params["end_time"],
                time_zone=params.get("time_zone", "UTC"),
                attendees=params.get("attendees"),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
