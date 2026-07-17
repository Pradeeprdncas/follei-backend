"""Unit tests for the ToolExecutor pipeline."""
import pytest
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.registry.registry import ToolRegistry
from mcp.executor.permissions import PermissionValidator
from mcp.executor.rate_limiter import RateLimiter
from mcp.executor.retry import RetryHandler
from mcp.executor.audit import AuditLogger
from mcp.executor.executor import ToolExecutor
from mcp.base.exceptions import PermissionDeniedError, RateLimitExceededError, ValidationError
from mcp.monitoring.metrics import get_in_memory_metrics


class SchemaDummyTool(MCPTool):
    """Dummy tool with a required parameter."""

    @property
    def name(self) -> str:
        return "schema_tool"

    @property
    def description(self) -> str:
        return "Requires field 'param1'"

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.EMAIL

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "required": ["param1"], "properties": {"param1": {"type": "string"}}}

    @property
    def output_schema(self) -> dict:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: dict) -> MCPResult:
        return MCPResult(success=True, data={"value": params["param1"]})


@pytest.mark.asyncio
async def test_executor_pipeline_success() -> None:
    registry = ToolRegistry()
    tool = SchemaDummyTool()
    await registry.register_tool(tool)
    
    executor = ToolExecutor(
        registry=registry,
        permission_validator=PermissionValidator(),
        rate_limiter=RateLimiter(),
        audit_logger=AuditLogger(),
        retry_handler=RetryHandler(min_wait=0.01),
    )
    
    context = MCPContext(
        organization_id="org_abc",
        user_id="user_xyz",
        agent_id="agent_123",
        permissions=["*"],
        request_id="req_999",
        trace_id="tr_999",
    )
    
    # 1. Success execution
    result = await executor.execute("schema_tool", context, {"param1": "hello"})
    assert result.success is True
    assert result.data["value"] == "hello"
    assert result.latency_ms > 0.0
    
    # Verify monitoring metric recorded
    metrics = get_in_memory_metrics()
    assert metrics["executions"].get("schema_tool", 0) > 0


@pytest.mark.asyncio
async def test_executor_pipeline_validation_error() -> None:
    registry = ToolRegistry()
    tool = SchemaDummyTool()
    await registry.register_tool(tool)
    
    executor = ToolExecutor(registry=registry)
    context = MCPContext(
        organization_id="org_abc",
        user_id="user_xyz",
        agent_id="agent_123",
        permissions=["*"],
        request_id="req_888",
        trace_id="tr_888",
    )
    
    # Missing required parameter "param1"
    result = await executor.execute("schema_tool", context, {})
    assert result.success is False
    assert "Missing required parameter" in result.error
    assert result.metadata["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_executor_pipeline_permission_denied() -> None:
    registry = ToolRegistry()
    tool = SchemaDummyTool()
    await registry.register_tool(tool)
    
    executor = ToolExecutor(registry=registry)
    context = MCPContext(
        organization_id="org_abc",
        user_id="user_xyz",
        agent_id="agent_123",
        permissions=["crm:*"],  # Wrong permission
        request_id="req_777",
        trace_id="tr_777",
    )
    
    result = await executor.execute("schema_tool", context, {"param1": "hello"})
    assert result.success is False
    assert "permission" in result.error.lower()
    assert result.metadata["error_type"] == "PermissionDeniedError"


@pytest.mark.asyncio
async def test_executor_pipeline_rate_limited() -> None:
    registry = ToolRegistry()
    tool = SchemaDummyTool()
    await registry.register_tool(tool)
    
    # Configure rate limiter with 0 capacity
    limiter = RateLimiter(default_rate=0.0, default_burst=0)
    
    executor = ToolExecutor(registry=registry, rate_limiter=limiter)
    context = MCPContext(
        organization_id="org_abc",
        user_id="user_xyz",
        agent_id="agent_123",
        permissions=["*"],
        request_id="req_666",
        trace_id="tr_666",
    )
    
    result = await executor.execute("schema_tool", context, {"param1": "hello"})
    assert result.success is False
    assert "rate limit exceeded" in result.error.lower()
    assert result.metadata["error_type"] == "RateLimitExceededError"
