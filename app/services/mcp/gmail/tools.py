"""Gmail MCP tools implementation."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.gmail.service import GmailService
from mcp.gmail.schemas import (
    SEND_EMAIL_SCHEMA,
    REPLY_EMAIL_SCHEMA,
    SEARCH_EMAIL_SCHEMA,
    READ_THREAD_SCHEMA,
)


class GmailSendEmailTool(MCPTool):
    """Tool to send a new email via Gmail."""

    def __init__(self, service: GmailService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "send_email"

    @property
    def description(self) -> str:
        return "Sends a new email message to the specified recipient."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEND_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"id": {"type": "string"}, "threadId": {"type": "string"}}}

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


class GmailReplyEmailTool(MCPTool):
    """Tool to reply to an email thread via Gmail."""

    def __init__(self, service: GmailService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "reply_email"

    @property
    def description(self) -> str:
        return "Replies to an existing email conversation thread."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return REPLY_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"id": {"type": "string"}, "threadId": {"type": "string"}}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.reply_email(
                thread_id=params["thread_id"],
                body=params["body"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class GmailSearchEmailTool(MCPTool):
    """Tool to search messages via Gmail."""

    def __init__(self, service: GmailService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "search_email"

    @property
    def description(self) -> str:
        return "Searches user emails using query criteria (e.g. from:address, has:attachment)."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEARCH_EMAIL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.search_emails(
                query=params["query"],
                max_results=params.get("max_results", 10),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class GmailReadThreadTool(MCPTool):
    """Tool to read a full thread via Gmail."""

    def __init__(self, service: GmailService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "read_thread"

    @property
    def description(self) -> str:
        return "Fetches all messages in an email thread to display a complete email conversation history."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> Dict[str, Any]:
        return READ_THREAD_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"messages": {"type": "array"}}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.read_thread(thread_id=params["thread_id"])
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
