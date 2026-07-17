"""Unit tests for MCPProtocolHandler state machine."""
import pytest
from mcp.server.protocol import MCPProtocolHandler, ProtocolState, ProtocolError


def test_protocol_lifecycle() -> None:
    handler = MCPProtocolHandler()
    assert handler.state == ProtocolState.UNINITIALIZED

    # Call initialize
    init_params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0.0"}
    }
    
    # Check permission validation checks before handshake is complete
    with pytest.raises(ProtocolError):
        handler.validate_request("tools/list")

    res = handler.handle_initialize(init_params)
    assert handler.state == ProtocolState.INITIALIZING
    assert res["protocolVersion"] == "2024-11-05"
    assert res["serverInfo"]["name"] == "follei-enterprise-mcp"

    # Attempt list tools before completing initialization
    with pytest.raises(ProtocolError):
        handler.validate_request("tools/list")

    # Complete initialization
    handler.handle_initialized_notification()
    assert handler.state == ProtocolState.INITIALIZED

    # Validate calls now permitted
    handler.validate_request("tools/list")
    handler.validate_request("tools/call")


def test_protocol_duplicate_initialize() -> None:
    handler = MCPProtocolHandler()
    handler.handle_initialize({"protocolVersion": "2024-11-05"})
    
    with pytest.raises(ProtocolError):
        handler.handle_initialize({"protocolVersion": "2024-11-05"})


def test_protocol_close() -> None:
    handler = MCPProtocolHandler()
    handler.close()
    assert handler.state == ProtocolState.CLOSED
    
    with pytest.raises(ProtocolError):
        handler.validate_request("initialize")
