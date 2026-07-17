"""MCP Protocol state machine and lifecycle validator."""
from enum import Enum
from typing import Any, Dict, Optional
from loguru import logger
from mcp.base.exceptions import MCPException


class ProtocolState(str, Enum):
    """The connection state of the Model Context Protocol session."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    CLOSED = "closed"


class ProtocolError(MCPException):
    """Protocol validation violation exception."""
    pass


class MCPProtocolHandler:
    """Manages protocol initialization lifecycle and validates method sequence."""

    def __init__(self) -> None:
        self._state: ProtocolState = ProtocolState.UNINITIALIZED
        self.client_capabilities: Dict[str, Any] = {}
        self.client_info: Dict[str, Any] = {}
        self.protocol_version: Optional[str] = None

    @property
    def state(self) -> ProtocolState:
        return self._state

    def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validates initialize parameters and transitions state to INITIALIZING."""
        if self._state != ProtocolState.UNINITIALIZED:
            raise ProtocolError("Server has already been initialized or is currently initializing.")

        self._state = ProtocolState.INITIALIZING
        self.protocol_version = params.get("protocolVersion")
        self.client_capabilities = params.get("capabilities", {})
        self.client_info = params.get("clientInfo", {})

        logger.info(
            f"Initializing MCP session. Client: {self.client_info.get('name', 'unknown')} "
            f"v{self.client_info.get('version', 'unknown')} using Protocol v{self.protocol_version}"
        )

        # Standard server version and capabilities
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
                "prompts": {"listChanged": True}
            },
            "serverInfo": {
                "name": "follei-enterprise-mcp",
                "version": "1.0.0"
            }
        }

    def handle_initialized_notification(self) -> None:
        """Transitions state to INITIALIZED after client receives initialization response."""
        if self._state != ProtocolState.INITIALIZING:
            raise ProtocolError(f"Cannot complete initialization from state: {self._state.value}")
        self._state = ProtocolState.INITIALIZED
        logger.info("MCP Session fully established (state = INITIALIZED).")

    def validate_request(self, method: str) -> None:
        """Verifies if the current protocol state permits calling the specified method."""
        if self._state == ProtocolState.CLOSED:
            raise ProtocolError("MCP session is closed.")

        if method == "initialize":
            if self._state != ProtocolState.UNINITIALIZED:
                raise ProtocolError("Server is already initialized.")
            return

        if self._state == ProtocolState.UNINITIALIZED:
            raise ProtocolError("You must call 'initialize' first before executing other methods.")

        if self._state == ProtocolState.INITIALIZING and method != "notifications/initialized":
            raise ProtocolError("Client must send 'notifications/initialized' to complete handshake.")

    def close(self) -> None:
        """Transitions connection to CLOSED."""
        self._state = ProtocolState.CLOSED
        logger.info("MCP session closed.")
