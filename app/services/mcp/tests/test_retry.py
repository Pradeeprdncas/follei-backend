"""Unit tests for the RetryHandler."""
import pytest
from mcp.executor.retry import RetryHandler
from mcp.base.exceptions import ConnectorError, ValidationError


@pytest.mark.asyncio
async def test_retry_handler_success_flow() -> None:
    handler = RetryHandler(max_attempts=3, min_wait=0.01, max_wait=0.05)
    call_count = 0
    
    async def op() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"
        
    res = await handler.execute_with_retry("test_op", op)
    assert res == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_handler_transient_failure_then_success() -> None:
    handler = RetryHandler(max_attempts=3, min_wait=0.01, max_wait=0.05)
    call_count = 0
    
    async def op() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectorError("Transient network failure")
        return "success"
        
    res = await handler.execute_with_retry("test_op", op)
    assert res == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_handler_permanent_failure() -> None:
    handler = RetryHandler(max_attempts=3, min_wait=0.01, max_wait=0.05)
    call_count = 0
    
    async def op() -> str:
        nonlocal call_count
        call_count += 1
        raise ConnectorError("Permanent database outage")
        
    with pytest.raises(ConnectorError):
        await handler.execute_with_retry("test_op", op)
        
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_handler_non_retriable_error() -> None:
    handler = RetryHandler(max_attempts=3, min_wait=0.01, max_wait=0.05)
    call_count = 0
    
    async def op() -> str:
        nonlocal call_count
        call_count += 1
        raise ValidationError("Invalid tool inputs")
        
    with pytest.raises(ValidationError):
        await handler.execute_with_retry("test_op", op)
        
    # Validation errors should fail instantly without retrying
    assert call_count == 1
