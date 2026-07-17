"""Audit logging for MCP tool execution pipeline."""
from typing import Any, Dict, Set
from loguru import logger
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult


class AuditLogger:
    """Logs tool execution start, success, and failures while scrubbing credentials."""

    def __init__(self, sensitive_keys: Set[str] = None) -> None:
        self.sensitive_keys = sensitive_keys or {
            "password",
            "token",
            "secret",
            "api_key",
            "authorization",
            "auth",
            "client_secret",
            "refresh_token",
            "access_token",
        }

    def redact(self, data: Any) -> Any:
        """Recursively redacts sensitive keys in dictionaries and structures."""
        if isinstance(data, dict):
            return {
                k: "******" if any(sk in k.lower() for sk in self.sensitive_keys)
                else self.redact(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self.redact(item) for item in data]
        return data

    async def log_start(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> None:
        """Logs the start of tool execution."""
        safe_params = self.redact(params)
        logger.info(
            f"[AUDIT] Tool '{tool_name}' starting execution. "
            f"ReqID: {context.request_id}, Org: {context.organization_id}, "
            f"User: {context.user_id}, Agent: {context.agent_id}, Trace: {context.trace_id}, "
            f"Params: {safe_params}"
        )

    async def log_success(
        self, tool_name: str, context: MCPContext, result: MCPResult
    ) -> None:
        """Logs a successful tool execution."""
        safe_data = self.redact(result.data)
        logger.info(
            f"[AUDIT] Tool '{tool_name}' completed successfully. "
            f"ReqID: {context.request_id}, Latency: {result.latency_ms:.2f}ms, "
            f"Result Data: {safe_data}"
        )

    async def log_failure(
        self, tool_name: str, context: MCPContext, exception: Exception, latency: float
    ) -> None:
        """Logs a failed tool execution."""
        logger.error(
            f"[AUDIT] Tool '{tool_name}' failed execution. "
            f"ReqID: {context.request_id}, Latency: {latency:.2f}ms, "
            f"Exception: {type(exception).__name__}, Message: {str(exception)}"
        )
