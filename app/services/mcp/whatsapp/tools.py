"""WhatsApp MCP tools implementation."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.whatsapp.service import WhatsAppService
from mcp.whatsapp.schemas import (
    WHATSAPP_SEND_MESSAGE_SCHEMA,
    WHATSAPP_SEND_TEMPLATE_SCHEMA,
    WHATSAPP_SEND_MEDIA_SCHEMA,
    WHATSAPP_GET_CONVERSATION_SCHEMA,
)


class WhatsAppSendMessageTool(MCPTool):
    """Tool to send a plain text message via WhatsApp Business API."""

    def __init__(self, service: WhatsAppService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "whatsapp_send_message"

    @property
    def description(self) -> str:
        return "Sends a WhatsApp text message to the specified contact number."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.WHATSAPP

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WHATSAPP_SEND_MESSAGE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_message(
                to=params["to"],
                body=params["body"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class WhatsAppSendTemplateTool(MCPTool):
    """Tool to send a template-based message via WhatsApp."""

    def __init__(self, service: WhatsAppService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "whatsapp_send_template"

    @property
    def description(self) -> str:
        return "Sends a pre-approved template notification to the contact phone number."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.WHATSAPP

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WHATSAPP_SEND_TEMPLATE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_template(
                to=params["to"],
                template_name=params["template_name"],
                language_code=params.get("language_code", "en_US"),
                components=params.get("components"),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class WhatsAppSendMediaTool(MCPTool):
    """Tool to send media files via WhatsApp."""

    def __init__(self, service: WhatsAppService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "whatsapp_send_media"

    @property
    def description(self) -> str:
        return "Sends an image, document, audio, or video link via WhatsApp."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.WHATSAPP

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WHATSAPP_SEND_MEDIA_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_media(
                to=params["to"],
                media_type=params["media_type"],
                media_url=params["media_url"],
                caption=params.get("caption"),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class WhatsAppGetConversationTool(MCPTool):
    """Tool to retrieve conversation history logs."""

    def __init__(self, service: WhatsAppService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "whatsapp_get_conversation"

    @property
    def description(self) -> str:
        return "Fetches details or historical message logs for a specific WhatsApp contact."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.WHATSAPP

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WHATSAPP_GET_CONVERSATION_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_conversation(
                phone_number=params["phone_number"],
                limit=params.get("limit", 10),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
