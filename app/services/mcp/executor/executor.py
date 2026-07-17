"""Tool Executor engine executing the tool pipeline."""
import time
from typing import Any, Dict, Optional
from loguru import logger
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.exceptions import MCPException, ValidationError
from mcp.registry.registry import ToolRegistry
from mcp.executor.permissions import PermissionValidator
from mcp.executor.rate_limiter import RateLimiter
from mcp.executor.retry import RetryHandler
from mcp.executor.audit import AuditLogger
from mcp.executor.cache import TTLCache
from mcp.executor.circuit_breaker import CircuitBreaker
from mcp.monitoring.metrics import (
    record_tool_execution,
    record_tool_failure,
    record_tool_duration,
)
from mcp.monitoring.tracing import trace_tool_execution


class ToolExecutor:
    """Pipelines tool executions through lookups, authentication, caching, circuit breakers, and monitoring."""

    def __init__(
        self,
        registry: ToolRegistry,
        permission_validator: PermissionValidator = None,
        rate_limiter: RateLimiter = None,
        audit_logger: AuditLogger = None,
        retry_handler: RetryHandler = None,
        cache: TTLCache = None,
        circuit_breaker: CircuitBreaker = None,
    ) -> None:
        self.registry = registry
        self.permission_validator = permission_validator or PermissionValidator()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.audit_logger = audit_logger or AuditLogger()
        self.retry_handler = retry_handler or RetryHandler()
        self.cache = cache or TTLCache()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def _validate_input_schema(self, tool_name: str, schema: Dict[str, Any], params: Dict[str, Any]) -> None:
        """Lightweight JSON schema-like validator to confirm required fields exist."""
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in params:
                raise ValidationError(f"Missing required parameter '{field}' for tool '{tool_name}'.")

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        """Executes a tool within the validated pipeline environment."""
        start_time = time.time()
        
        # 1. Cache Lookup for Read-Only operations
        is_read_operation = any(prefix in tool_name for prefix in ("list", "search", "read", "get"))
        cache_key = f"{tool_name}:{str(sorted(params.items()))}"
        
        if is_read_operation:
            cached_res = await self.cache.get(cache_key)
            if cached_res is not None:
                logger.info(f"Cache HIT for tool: {tool_name}")
                return cached_res

        record_tool_execution(tool_name)
        await self.audit_logger.log_start(tool_name, context, params)
        
        try:
            # 2. Lookup Tool
            tool = await self.registry.get_tool(tool_name)
            
            # 3. Schema Validation
            self._validate_input_schema(tool_name, tool.input_schema, params)
            
            # 4. Permission Validation
            await self.permission_validator.validate(tool, context)
            
            # 5. Rate Limit Validation
            await self.rate_limiter.validate(tool, context)

            # 6. Circuit Breaker validation
            await self.circuit_breaker.before_execute()
            
            # 7. Execute tool under a retry wrapper using OpenTelemetry tracing
            async def _run_operation() -> MCPResult:
                async with trace_tool_execution(tool_name, context):
                    return await tool.execute(context, params)
                    
            try:
                result = await self.retry_handler.execute_with_retry(tool_name, _run_operation)
            except Exception as execution_err:
                await self.circuit_breaker.record_failure()
                raise execution_err

            if result.success:
                await self.circuit_breaker.record_success()
                # Store back to Cache
                if is_read_operation:
                    await self.cache.set(cache_key, result)
            else:
                await self.circuit_breaker.record_failure()

            # Record latency metrics and log success
            latency = (time.time() - start_time) * 1000.0
            result.latency_ms = latency
            record_tool_duration(tool_name, latency)
            await self.audit_logger.log_success(tool_name, context, result)
            return result
            
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            record_tool_failure(tool_name, type(e).__name__)
            await self.audit_logger.log_failure(tool_name, context, e, latency)
            
            error_msg = str(e)
            if isinstance(e, MCPException):
                return MCPResult(
                    success=False,
                    error=error_msg,
                    latency_ms=latency,
                    metadata={"error_type": type(e).__name__},
                )
            
            return MCPResult(
                success=False,
                error=f"Internal executor failure: {error_msg}",
                latency_ms=latency,
                metadata={"error_type": type(e).__name__},
            )
        
    async def execute_tool(self, tool_name: str, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        """Alias for execute() to support multiple naming patterns if needed."""
        return await self.execute(tool_name, context, params)
