"""OpenTelemetry tracing context manager for tool execution pipeline."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from loguru import logger
from mcp.base.context import MCPContext

try:
    from opentelemetry import trace
    OPENTELEMETRY_AVAILABLE = True
    tracer = trace.get_tracer("follei.mcp")
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    tracer = None


@asynccontextmanager
async def trace_tool_execution(
    tool_name: str, context: MCPContext
) -> AsyncGenerator[None, None]:
    """Asynchronous context manager to trace execution of a tool.

    Leverages OpenTelemetry if available; falls back to debug log tracing.
    """
    if OPENTELEMETRY_AVAILABLE and tracer:
        # Create a span with trace ID and organization metadata context
        span_name = f"mcp.tool_execute.{tool_name}"
        # Parse existing trace ID if format allows, else let OTel handle propagation
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("tool.name", tool_name)
            span.set_attribute("mcp.organization_id", context.organization_id)
            span.set_attribute("mcp.user_id", context.user_id)
            span.set_attribute("mcp.agent_id", context.agent_id)
            span.set_attribute("mcp.request_id", context.request_id)
            span.set_attribute("mcp.trace_id", context.trace_id)
            try:
                yield
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.status.Status(trace.status.StatusCode.ERROR, str(e)))
                raise
    else:
        # Fallback to logger instrumentation
        logger.debug(
            f"[TRACE START] Tool '{tool_name}' under Request ID '{context.request_id}', Trace ID '{context.trace_id}'"
        )
        try:
            yield
        finally:
            logger.debug(
                f"[TRACE END] Tool '{tool_name}' under Request ID '{context.request_id}'"
            )
        return
