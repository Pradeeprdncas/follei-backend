"""Unit tests for the permissions validator."""
import pytest
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.executor.permissions import PermissionValidator
from mcp.base.exceptions import PermissionDeniedError
from mcp.tests.test_registry import DummyTool


@pytest.mark.asyncio
async def test_permission_validator_rules() -> None:
    validator = PermissionValidator()
    tool = DummyTool("send_email", MCPCapability.EMAIL)
    
    # 1. Success case: Wildcard '*'
    ctx_wildcard = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=["*"],
        request_id="req_1",
        trace_id="tr_1",
    )
    await validator.validate(tool, ctx_wildcard)
    
    # 2. Success case: Capability Wildcard 'email:*'
    ctx_cap = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=["email:*"],
        request_id="req_2",
        trace_id="tr_2",
    )
    await validator.validate(tool, ctx_cap)
    
    # 3. Success case: Exact Permission 'email:send_email'
    ctx_exact = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=["email:send_email"],
        request_id="req_3",
        trace_id="tr_3",
    )
    await validator.validate(tool, ctx_exact)

    # 4. Success case: Tool Name 'send_email'
    ctx_name = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=["send_email"],
        request_id="req_4",
        trace_id="tr_4",
    )
    await validator.validate(tool, ctx_name)

    # 5. Failure case: Wrong capability permission
    ctx_wrong = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=["crm:*"],
        request_id="req_5",
        trace_id="tr_5",
    )
    with pytest.raises(PermissionDeniedError):
        await validator.validate(tool, ctx_wrong)

    # 6. Failure case: Empty permissions list
    ctx_empty = MCPContext(
        organization_id="org_1",
        user_id="user_1",
        agent_id="agent_1",
        permissions=[],
        request_id="req_6",
        trace_id="tr_6",
    )
    with pytest.raises(PermissionDeniedError):
        await validator.validate(tool, ctx_empty)
