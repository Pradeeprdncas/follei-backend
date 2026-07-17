"""Unit tests for MCPServer, transports, and auth middleware."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from mcp.base.context import MCPContext
from mcp.base.tool import MCPTool
from mcp.base.capability import MCPCapability
from mcp.base.result import MCPResult
from mcp.server.server import MCPServer
from mcp.server.jsonrpc import make_success_response
from mcp.server.middleware import extract_mcp_context


class MockTool(MCPTool):
    @property
    def name(self) -> str:
        return "mock_test_tool"
    @property
    def description(self) -> str:
        return "A mock tool for unit testing server routing"
    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.COLLABORATION
    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]}
    @property
    def output_schema(self) -> dict:
        return {"type": "object"}
    async def execute(self, context: MCPContext, params: dict) -> MCPResult:
        return MCPResult(success=True, data={"reply": f"Received: {params['msg']}"})


@pytest.fixture
def mcp_server() -> MCPServer:
    server = MCPServer()
    # Manually register the mock tool for testing
    asyncio.run(server.tool_registry.register_tool(MockTool()))
    return server


@pytest.fixture
def client(mcp_server) -> TestClient:
    return TestClient(mcp_server.app)


def test_health_check(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "registered_tools" in data


def test_metrics_endpoint(client) -> None:
    res = client.get("/metrics")
    assert res.status_code == 200


def test_http_transport_flow(client) -> None:
    # 1. Send initialize
    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": 1
    }
    headers = {"Authorization": "Bearer enterprise-mcp-secret-token"}
    res = client.post("/mcp", json=init_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    assert data["result"]["protocolVersion"] == "2024-11-05"

    # 2. Complete initialized notification
    notif_payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    res = client.post("/mcp", json=notif_payload, headers=headers)
    assert res.status_code == 204

    # 3. List tools
    list_payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }
    res = client.post("/mcp", json=list_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    assert any(t["name"] == "mock_test_tool" for t in data["result"]["tools"])

    # 4. Call tool
    call_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "mock_test_tool",
            "arguments": {"msg": "Hello Server"}
        },
        "id": 3
    }
    res = client.post("/mcp", json=call_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    assert "content" in data["result"]
    assert "Received: Hello Server" in data["result"]["content"][0]["text"]


def test_auth_middleware_failures(client) -> None:
    # Test wrong token raising 401
    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
        "id": 1
    }
    res = client.post("/mcp", json=init_payload, headers={"Authorization": "Bearer wrong-token"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_stdio_transport_loop() -> None:
    server = MCPServer()
    await server.tool_registry.register_tool(MockTool())
    
    mock_reader = AsyncMock()
    # Feed an initialize line, then EOF
    init_line = json.dumps({
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
        "id": 1
    }).encode("utf-8") + b"\n"
    
    mock_reader.readline.side_effect = [init_line, b""]
    
    mock_stdout = MagicMock()
    
    transport = server.stdio_transport
    transport._running = True
    
    with patch("asyncio.StreamReader", return_value=mock_reader), \
         patch("sys.stdin", MagicMock()), \
         patch("sys.__stdout__", mock_stdout):
        
        await transport._read_loop()
        
        # Verify stdout received a reply frame
        assert mock_stdout.write.called
        args, _ = mock_stdout.write.call_args
        reply_data = json.loads(args[0].strip())
        assert reply_data["id"] == 1
        assert "result" in reply_data
