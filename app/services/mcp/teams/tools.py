"""Microsoft Teams MCP tool implementations."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.teams.service import TeamsService
from mcp.teams.schemas import (
    SEND_MESSAGE_SCHEMA,
    LIST_TEAMS_SCHEMA,
    LIST_CHANNELS_SCHEMA,
    GET_MESSAGES_SCHEMA,
    CREATE_CHANNEL_SCHEMA,
    ADD_MEMBER_SCHEMA,
    SCHEDULE_MEETING_SCHEMA,
)


class TeamsSendMessageTool(MCPTool):
    """Sends a message."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_send_message"

    @property
    def description(self) -> str:
        return "Sends a chat message to a Microsoft Teams chat or channel."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEND_MESSAGE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.send_message(
                text=params["text"],
                chat_id=params.get("chat_id"),
                channel_id=params.get("channel_id"),
                team_id=params.get("team_id")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsListTeamsTool(MCPTool):
    """Lists joined teams."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_list_teams"

    @property
    def description(self) -> str:
        return "Lists the joined Microsoft Teams for the authenticated user."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return LIST_TEAMS_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.list_teams()
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsListChannelsTool(MCPTool):
    """Lists channels in a team."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_list_channels"

    @property
    def description(self) -> str:
        return "Lists channels inside a specific Microsoft Team."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return LIST_CHANNELS_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.list_channels(
                team_id=params["team_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsGetMessagesTool(MCPTool):
    """Gets message logs."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_get_messages"

    @property
    def description(self) -> str:
        return "Retrieves message history logs from Microsoft Teams chats or channels."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_MESSAGES_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_messages(
                chat_id=params.get("chat_id"),
                channel_id=params.get("channel_id"),
                team_id=params.get("team_id"),
                limit=params.get("limit", 20)
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsCreateChannelTool(MCPTool):
    """Creates channel."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_create_channel"

    @property
    def description(self) -> str:
        return "Creates a new channel in a Microsoft Team."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_CHANNEL_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_channel(
                team_id=params["team_id"],
                name=params["name"],
                description=params.get("description")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsAddMemberTool(MCPTool):
    """Adds member."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_add_member"

    @property
    def description(self) -> str:
        return "Adds a user conversation member to a Microsoft Team."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return ADD_MEMBER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.add_member(
                team_id=params["team_id"],
                user_id=params["user_id"],
                roles=params.get("roles")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class TeamsScheduleMeetingTool(MCPTool):
    """Schedules online meeting."""

    def __init__(self, service: TeamsService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "teams_schedule_meeting"

    @property
    def description(self) -> str:
        return "Schedules an online virtual meeting via Microsoft Teams."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SCHEDULE_MEETING_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.schedule_meeting(
                subject=params["subject"],
                start_time=params["start_time"],
                end_time=params["end_time"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
