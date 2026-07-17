"""Calendar MCP tools implementation."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.calendar.service import CalendarService
from mcp.calendar.schemas import (
    CALENDAR_CREATE_EVENT_SCHEMA,
    CALENDAR_UPDATE_EVENT_SCHEMA,
    CALENDAR_CANCEL_EVENT_SCHEMA,
    CALENDAR_GET_AVAILABILITY_SCHEMA,
)


class CalendarCreateEventTool(MCPTool):
    """Tool to create a calendar event (Google/Outlook)."""

    def __init__(self, service: CalendarService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "create_event"

    @property
    def description(self) -> str:
        return "Creates a new calendar event on Google Calendar or Outlook Calendar."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CALENDAR

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CALENDAR_CREATE_EVENT_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_event(
                provider=params["provider"],
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


class CalendarUpdateEventTool(MCPTool):
    """Tool to update an existing calendar event (Google/Outlook)."""

    def __init__(self, service: CalendarService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "update_event"

    @property
    def description(self) -> str:
        return "Updates properties of an existing Google Calendar or Outlook Calendar event."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CALENDAR

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CALENDAR_UPDATE_EVENT_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.update_event(
                provider=params["provider"],
                event_id=params["event_id"],
                event_data=params["event_data"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CalendarCancelEventTool(MCPTool):
    """Tool to cancel/delete a calendar event."""

    def __init__(self, service: CalendarService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "cancel_event"

    @property
    def description(self) -> str:
        return "Cancels or deletes a scheduled calendar event."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CALENDAR

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CALENDAR_CANCEL_EVENT_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.cancel_event(
                provider=params["provider"],
                event_id=params["event_id"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CalendarGetAvailabilityTool(MCPTool):
    """Tool to query participant availability schedule slots."""

    def __init__(self, service: CalendarService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "get_availability"

    @property
    def description(self) -> str:
        return "Queries the free/busy schedule slots of participants in a specific time window."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CALENDAR

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CALENDAR_GET_AVAILABILITY_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_availability(
                provider=params["provider"],
                start_time=params["start_time"],
                end_time=params["end_time"],
                emails=params["emails"],
                time_zone=params.get("time_zone", "UTC"),
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
