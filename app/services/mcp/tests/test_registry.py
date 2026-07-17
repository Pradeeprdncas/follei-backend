"""Unit tests for ToolRegistry and auto-discovery."""
import pytest
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.registry.registry import ToolRegistry
from mcp.registry.discovery import discover_and_register
from mcp.base.exceptions import ToolNotFoundError
from mcp.base.connector import MCPConnector


class DummyTool(MCPTool):
    """Dummy tool for testing registration."""

    def __init__(self, name: str, capability: MCPCapability) -> None:
        self._name = name
        self._capability = capability

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Dummy description for {self._name}"

    @property
    def capability(self) -> MCPCapability:
        return self._capability

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    @property
    def output_schema(self) -> dict:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: dict) -> MCPResult:
        return MCPResult(success=True, data={"result": "success"})


class DummyConnector(MCPConnector):
    """Dummy connector for testing discovery."""

    def __init__(self, name: str, tools: list) -> None:
        self._name = name
        self._tools = tools
        self.connected = False

    @property
    def name(self) -> str:
        return self._name

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return True

    async def refresh_token(self) -> None:
        pass

    def get_tools(self) -> list:
        return self._tools

    async def execute(self, tool_name: str, context: MCPContext, params: dict) -> MCPResult:
        for tool in self._tools:
            if tool.name == tool_name:
                return await tool.execute(context, params)
        raise ToolNotFoundError()


@pytest.mark.asyncio
async def test_tool_registration_and_retrieval() -> None:
    registry = ToolRegistry()
    tool = DummyTool("test_tool", MCPCapability.EMAIL)
    
    # Register tool
    await registry.register_tool(tool)
    
    # Retrieve tool
    fetched = await registry.get_tool("test_tool")
    assert fetched.name == "test_tool"
    assert fetched.capability == MCPCapability.EMAIL
    
    # List tools
    all_tools = await registry.list_tools()
    assert len(all_tools) == 1
    assert all_tools[0].name == "test_tool"
    
    # Unregister tool
    await registry.unregister_tool("test_tool")
    with pytest.raises(ToolNotFoundError):
        await registry.get_tool("test_tool")


@pytest.mark.asyncio
async def test_registry_search_and_capabilities() -> None:
    registry = ToolRegistry()
    t1 = DummyTool("send_email", MCPCapability.EMAIL)
    t2 = DummyTool("create_event", MCPCapability.CALENDAR)
    
    await registry.register_tool(t1)
    await registry.register_tool(t2)
    
    # Search tool
    results = await registry.search_tools("email")
    assert len(results) == 1
    assert results[0].name == "send_email"
    
    # Capability filtering
    email_tools = await registry.get_tools_by_capability(MCPCapability.EMAIL)
    assert len(email_tools) == 1
    assert email_tools[0].name == "send_email"
    
    calendar_tools = await registry.get_tools_by_capability(MCPCapability.CALENDAR)
    assert len(calendar_tools) == 1
    assert calendar_tools[0].name == "create_event"


@pytest.mark.asyncio
async def test_connector_discovery() -> None:
    registry = ToolRegistry()
    t1 = DummyTool("c1_tool", MCPCapability.CRM)
    connector = DummyConnector("mock_crm", [t1])
    
    # Auto discovery execution
    await discover_and_register(registry, [connector])
    
    # Assert connector connect was invoked
    assert connector.connected is True
    
    # Assert tool was registered successfully
    tool = await registry.get_tool("c1_tool")
    assert tool.name == "c1_tool"
    assert tool.capability == MCPCapability.CRM
