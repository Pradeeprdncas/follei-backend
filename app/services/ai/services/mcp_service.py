"""MCP Service - Production Model Context Protocol adapter with graceful degradation."""
from typing import Dict, Any, List, Optional
from loguru import logger


class MCPService:
    """Production MCP service with graceful skip.

    - connect(): Establish MCP connection
    - list_tools(): List available tools
    - health(): Return health status
    Never crashes startup.
    """

    def __init__(self):
        self._client = None
        self._enabled = True
        self._configured = False
        self._tools: List[str] = []
        self._init()

    def _init(self):
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            mcp_enabled = getattr(settings, 'MCP_ENABLED', None)
            self._enabled = mcp_enabled is not False  # Default enabled if configured
            self._configured = True
        except Exception:
            self._enabled = False
            self._configured = False

    def connect(self):
        """Establish MCP connection."""
        if not self._enabled:
            return False
        try:
            # Try to import and initialize MCP
            try:
                from app.services.ai.mcp_adapter import MCPToolAdapter
                self._client = MCPToolAdapter()
                self._tools = self._client.list_tools() if hasattr(self._client, 'list_tools') else []
                return True
            except ImportError:
                logger.warning("MCP adapter not available, using stub")
                self._client = None
                self._tools = []
                return True  # Don't fail startup
        except Exception as e:
            logger.warning(f"MCP connection failed: {e}")
            self._enabled = False
            return False

    def list_tools(self) -> List[str]:
        """List available MCP tools."""
        return self._tools

    def health(self) -> Dict[str, Any]:
        """Get MCP health status."""
        try:
            if self._client is not None:
                return {"mcp": "healthy", "status": "ok", "tools": len(self._tools)}
        except Exception:
            pass
        if not self._enabled:
            return {"mcp": "disabled", "status": "skipped"}
        return {"mcp": "unavailable", "status": "degraded"}


# Singleton
_mcp_service: MCPService = None


def get_mcp_service() -> MCPService:
    """Get or create singleton MCP service."""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPService()
    return _mcp_service