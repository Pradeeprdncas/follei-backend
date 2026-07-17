"""Circuit Breaker pattern utility for external service calls."""
import asyncio
import time
from enum import Enum
from mcp.base.exceptions import ExecutionError


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreakerOpenException(ExecutionError):
    """Exception raised when circuit breaker trips open."""
    pass


class CircuitBreaker:
    """Isolates failing connectors when exception limits are breached."""

    def __init__(
        self, failure_threshold: int = 5, recovery_timeout: float = 30.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def before_execute(self) -> None:
        """Validates circuit status, updating states if recovery times are crossed."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() > self.last_failure_time + self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger_msg = "Circuit Breaker transitioned to HALF-OPEN. Probing connection health..."
                    from loguru import logger
                    logger.warning(logger_msg)
                else:
                    raise CircuitBreakerOpenException("Circuit Breaker is OPEN. Downstream execution blocked.")

    async def record_success(self) -> None:
        """Resets failure counts upon successful executions."""
        async with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                from loguru import logger
                logger.info("Circuit Breaker returned to CLOSED state. Integration is healthy.")

    async def record_failure(self) -> None:
        """Increments failures, tripping open when threshold limits are exceeded."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger_msg = f"Circuit Breaker TRIPPED to OPEN state. Limit of {self.failure_threshold} failures exceeded."
                    from loguru import logger
                    logger.error(logger_msg)
