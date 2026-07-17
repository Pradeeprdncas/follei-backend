"""Permissions validation for MCP Tool Execution."""
from mcp.base.tool import MCPTool
from mcp.base.context import MCPContext
from mcp.base.exceptions import PermissionDeniedError


class PermissionValidator:
    """Validates if execution context permissions grant access to a specific tool."""

    async def validate(self, tool: MCPTool, context: MCPContext) -> None:
        """Validates if context.permissions matches the tool execution requirements.

        Raises PermissionDeniedError if unauthorized.
        """
        required_exact = f"{tool.capability.value}:{tool.name}"
        required_capability = f"{tool.capability.value}:*"
        
        # Check permissions list
        allowed = False
        for perm in context.permissions:
            if perm == "*" or perm == required_capability or perm == required_exact or perm == tool.name:
                allowed = True
                break
                
        if not allowed:
            raise PermissionDeniedError(
                f"Agent/User lacks permission to run tool '{tool.name}'. "
                f"Required permission: '{required_exact}' or '{required_capability}'."
            )
