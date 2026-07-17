"""Slack MCP Tool implementations."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.slack.service import SlackService
from mcp.slack.schemas import (
    SEND_MESSAGE_SCHEMA,
    LIST_CHANNELS_SCHEMA,
    GET_CHANNEL_MESSAGES_SCHEMA,
    CREATE_CHANNEL_SCHEMA,
    INVITE_USER_SCHEMA,
    GET_USER_INFO_SCHEMA,
    SEARCH_MESSAGES_SCHEMA,
    UPLOAD_FILE_SCHEMA,
    SCHEDULE_MESSAGE_SCHEMA,
)


class SlackSendMessageTool(MCPTool):
    """Sends a Slack message."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_send_message"

    @property
    def description(self) -> str:
        return "Sends a chat message to a Slack channel."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEND_MESSAGE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_message(
                channel=params["channel"],
                text=params["text"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackListChannelsTool(MCPTool):
    """Lists public Slack channels."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_list_channels"

    @property
    def description(self) -> str:
        return "Lists public/private channels in the Slack workspace."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return LIST_CHANNELS_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.list_channels(
                types=params.get("types", "public_channel")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackGetChannelMessagesTool(MCPTool):
    """Gets message logs from a channel."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_get_channel_messages"

    @property
    def description(self) -> str:
        return "Retrieves message history logs of a channel."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_CHANNEL_MESSAGES_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_channel_messages(
                channel=params["channel"],
                limit=params.get("limit", 20)
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackCreateChannelTool(MCPTool):
    """Creates a channel."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_create_channel"

    @property
    def description(self) -> str:
        return "Creates a new public or private Slack channel."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_CHANNEL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_channel(
                name=params["name"],
                is_private=params.get("is_private", False)
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackInviteUserTool(MCPTool):
    """Invites a user to a Slack channel."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_invite_user"

    @property
    def description(self) -> str:
        return "Invites an existing user into a specific Slack channel."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return INVITE_USER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.invite_user(
                channel=params["channel"],
                user_id=params["user_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackGetUserInfoTool(MCPTool):
    """Retrieves metadata user profile."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_get_user_info"

    @property
    def description(self) -> str:
        return "Retrieves profile details and metadata for a Slack user."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_USER_INFO_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_user_info(
                user_id=params["user_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackSearchMessagesTool(MCPTool):
    """Searches messages."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_search_messages"

    @property
    def description(self) -> str:
        return "Searches message contents across the Slack workspace."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEARCH_MESSAGES_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.search_messages(
                query=params["query"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackUploadFileTool(MCPTool):
    """Uploads a text file snippet."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_upload_file"

    @property
    def description(self) -> str:
        return "Uploads a text file or file snippet to selected channels."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return UPLOAD_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.upload_file(
                channels=params["channels"],
                content=params["content"],
                filename=params["filename"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class SlackScheduleMessageTool(MCPTool):
    """Schedules message."""

    def __init__(self, service: SlackService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "slack_schedule_message"

    @property
    def description(self) -> str:
        return "Schedules a message to post at a specific future unix timestamp."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CHAT

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SCHEDULE_MESSAGE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.schedule_message(
                channel=params["channel"],
                text=params["text"],
                post_at=params["post_at"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
