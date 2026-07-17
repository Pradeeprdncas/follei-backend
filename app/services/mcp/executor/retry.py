"""Async retry handler with exponential backoff for transient failures."""
import asyncio
from typing import Callable, Any
from loguru import logger
from mcp.base.exceptions import ConnectorError, ExecutionError


class RetryHandler:
    """Orchestrates exponential backoff for executions prone to transient network errors."""

    def __init__(
        self,
        max_attempts: int = 3,
        multiplier: float = 1.5,
        min_wait: float = 0.5,
        max_wait: float = 5.0,
    ) -> None:
        """Initializes the retry handler."""
        self.max_attempts = max_attempts
        self.multiplier = multiplier
        self.min_wait = min_wait
        self.max_wait = max_wait

    async def execute_with_retry(
        self, tool_name: str, operation: Callable[[], Any]
    ) -> Any:
        """Executes the callable, retrying if it raises ConnectorError or ExecutionError."""
        attempt = 0
        wait_time = self.min_wait
        
        while True:
            try:
                attempt += 1
                return await operation()
            except (ConnectorError, ExecutionError) as e:
                if attempt >= self.max_attempts:
                    logger.error(
                        f"Tool '{tool_name}' failed after {attempt} attempts: {e}"
                    )
                    raise e
                    
                logger.warning(
                    f"Tool '{tool_name}' failed with {type(e).__name__} (attempt {attempt}/{self.max_attempts}). "
                    f"Retrying in {wait_time:.2f}s... Error details: {e}"
                )
                await asyncio.sleep(wait_time)
                wait_time = min(wait_time * self.multiplier, self.max_wait)
            except Exception as e:
                # Other exceptions (like PermissionDeniedError, ValidationError) are not retried
                raise e
