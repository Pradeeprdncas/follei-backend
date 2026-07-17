"""Prometheus metrics logging for MCP tool execution."""
import threading
from typing import Any, Dict

# Try to import prometheus_client safely
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


if PROMETHEUS_AVAILABLE:
    # Define metrics using the prometheus_client package
    TOOL_EXECUTION_TOTAL = Counter(
        "tool_execution_total",
        "Total number of times a tool is executed",
        ["tool_name"],
    )
    TOOL_FAILURE_TOTAL = Counter(
        "tool_failure_total",
        "Total number of failures during tool execution",
        ["tool_name", "error_type"],
    )
    TOOL_EXECUTION_DURATION = Histogram(
        "tool_execution_duration_seconds",
        "Latency of tool execution in seconds",
        ["tool_name"],
    )
    CONNECTOR_HEALTH = Gauge(
        "connector_health",
        "Health status of the connector (1 for healthy, 0 for unhealthy)",
        ["connector_name"],
    )
else:
    # Mock fallback to in-memory metrics storage to ensure zero compile-time dependencies
    TOOL_EXECUTION_TOTAL = None
    TOOL_FAILURE_TOTAL = None
    TOOL_EXECUTION_DURATION = None
    CONNECTOR_HEALTH = None


# Thread-safe in-memory metrics tracker for fallback or validation
_in_memory_metrics: Dict[str, Dict[str, Any]] = {
    "executions": {},
    "failures": {},
    "durations": {},
    "health": {},
}
_metrics_lock = threading.Lock()


def record_tool_execution(tool_name: str) -> None:
    """Records starting tool execution."""
    if PROMETHEUS_AVAILABLE and TOOL_EXECUTION_TOTAL:
        TOOL_EXECUTION_TOTAL.labels(tool_name=tool_name).inc()
        
    with _metrics_lock:
        executions = _in_memory_metrics["executions"]
        executions[tool_name] = executions.get(tool_name, 0) + 1


def record_tool_failure(tool_name: str, error_type: str) -> None:
    """Records tool execution failure."""
    if PROMETHEUS_AVAILABLE and TOOL_FAILURE_TOTAL:
        TOOL_FAILURE_TOTAL.labels(tool_name=tool_name, error_type=error_type).inc()
        
    with _metrics_lock:
        failures = _in_memory_metrics["failures"]
        key = f"{tool_name}:{error_type}"
        failures[key] = failures.get(key, 0) + 1


def record_tool_duration(tool_name: str, duration_ms: float) -> None:
    """Records tool execution duration."""
    if PROMETHEUS_AVAILABLE and TOOL_EXECUTION_DURATION:
        # Prometheus histograms expect seconds
        TOOL_EXECUTION_DURATION.labels(tool_name=tool_name).observe(duration_ms / 1000.0)
        
    with _metrics_lock:
        durations = _in_memory_metrics["durations"]
        if tool_name not in durations:
            durations[tool_name] = []
        durations[tool_name].append(duration_ms)


def record_connector_health(connector_name: str, is_healthy: bool) -> None:
    """Records connector health metric."""
    status_val = 1.0 if is_healthy else 0.0
    if PROMETHEUS_AVAILABLE and CONNECTOR_HEALTH:
        CONNECTOR_HEALTH.labels(connector_name=connector_name).set(status_val)
        
    with _metrics_lock:
        _in_memory_metrics["health"][connector_name] = status_val


def get_in_memory_metrics() -> Dict[str, Dict[str, Any]]:
    """Retrieves in-memory statistics (useful for tests and monitoring fallbacks)."""
    with _metrics_lock:
        # Deep copy structure
        return {
            "executions": dict(_in_memory_metrics["executions"]),
            "failures": dict(_in_memory_metrics["failures"]),
            "durations": {k: list(v) for k, v in _in_memory_metrics["durations"].items()},
            "health": dict(_in_memory_metrics["health"]),
        }
