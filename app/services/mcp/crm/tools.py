"""CRM MCP tools implementation."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.crm.service import CRMService
from mcp.crm.schemas import (
    CRM_CREATE_LEAD_SCHEMA,
    CRM_UPDATE_LEAD_SCHEMA,
    CRM_SEARCH_CONTACT_SCHEMA,
    CRM_CREATE_OPPORTUNITY_SCHEMA,
    CRM_UPDATE_OPPORTUNITY_SCHEMA,
)


class CRMCreateLeadTool(MCPTool):
    """Tool to create a CRM Lead."""

    def __init__(self, service: CRMService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "create_lead"

    @property
    def description(self) -> str:
        return "Creates a new lead/contact record in the CRM."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CRM_CREATE_LEAD_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_lead(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CRMUpdateLeadTool(MCPTool):
    """Tool to update a CRM Lead."""

    def __init__(self, service: CRMService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "update_lead"

    @property
    def description(self) -> str:
        return "Updates properties of an existing CRM lead/contact record."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CRM_UPDATE_LEAD_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.update_lead(
                lead_id=params["lead_id"],
                lead_data=params["lead_data"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CRMSearchContactTool(MCPTool):
    """Tool to search CRM contacts."""

    def __init__(self, service: CRMService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "search_contact"

    @property
    def description(self) -> str:
        return "Searches contacts in the CRM matching query terms."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CRM_SEARCH_CONTACT_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.search_contact(query=params["query"])
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CRMCreateOpportunityTool(MCPTool):
    """Tool to create a CRM Opportunity."""

    def __init__(self, service: CRMService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "create_opportunity"

    @property
    def description(self) -> str:
        return "Creates a new sales opportunity or deal in the CRM."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CRM_CREATE_OPPORTUNITY_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_opportunity(params)
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class CRMUpdateOpportunityTool(MCPTool):
    """Tool to update a CRM Opportunity."""

    def __init__(self, service: CRMService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "update_opportunity"

    @property
    def description(self) -> str:
        return "Updates properties of an existing opportunity or deal."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.CRM

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CRM_UPDATE_OPPORTUNITY_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.update_opportunity(
                opp_id=params["opp_id"],
                opp_data=params["opp_data"],
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
