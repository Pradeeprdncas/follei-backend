"""Thread-safe Tool Registry implementation."""
import asyncio
from typing import Dict, List, Optional
from mcp.base.tool import MCPTool
from mcp.base.capability import MCPCapability
from mcp.base.exceptions import ToolNotFoundError


class ToolRegistry:
    """Thread-safe and async-safe repository of executable MCP tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}
        self._lock = asyncio.Lock()

    async def register_tool(self, tool: MCPTool) -> None:
        """Registers a tool with the framework registry."""
        async with self._lock:
            self._tools[tool.name] = tool

    async def unregister_tool(self, tool_name: str) -> None:
        """Deregisters a tool from the registry."""
        async with self._lock:
            if tool_name in self._tools:
                del self._tools[tool_name]

    async def get_tool(self, tool_name: str) -> MCPTool:
        """Retrieves a specific tool by name, raising ToolNotFoundError if not found."""
        async with self._lock:
            if tool_name not in self._tools:
                raise ToolNotFoundError(f"Tool '{tool_name}' is not registered.")
            return self._tools[tool_name]

    async def list_tools(self) -> List[MCPTool]:
        """Lists all registered tools."""
        async with self._lock:
            return list(self._tools.values())

    async def search_tools(self, query: str) -> List[MCPTool]:
        """Searches tools by matching a text query against name or description."""
        async with self._lock:
            q = query.lower()
            return [
                t for t in self._tools.values()
                if q in t.name.lower() or q in t.description.lower()
            ]

    async def get_tools_by_capability(self, capability: MCPCapability) -> List[MCPTool]:
        """Gets all tools categorised under a specific capability."""
        async with self._lock:
            return [t for t in self._tools.values() if t.capability == capability]
