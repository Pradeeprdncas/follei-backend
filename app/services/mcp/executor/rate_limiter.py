"""Rate limiting logic for tool execution."""
import asyncio
import time
from typing import Dict, Tuple
from mcp.base.tool import MCPTool
from mcp.base.context import MCPContext
from mcp.base.exceptions import RateLimitExceededError


class RateLimiter:
    """Token Bucket rate limiter for MCP tool executions."""

    def __init__(self, default_rate: float = 10.0, default_burst: int = 20) -> None:
        """Initializes the rate limiter.

        Args:
            default_rate: Number of tokens added per second.
            default_burst: Maximum token capacity.
        """
        self.default_rate = default_rate
        self.default_burst = default_burst
        self.buckets: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.lock = asyncio.Lock()

    async def validate(self, tool: MCPTool, context: MCPContext) -> None:
        """Validates if the user is within rate limits.

        Raises RateLimitExceededError if throttled.
        """
        async with self.lock:
            key = (context.user_id, tool.name)
            now = time.time()
            
            rate = self.default_rate
            burst = self.default_burst
            
            if key not in self.buckets:
                tokens = float(burst)
            else:
                last_tokens, last_time = self.buckets[key]
                elapsed = now - last_time
                tokens = min(float(burst), last_tokens + (elapsed * rate))
                
            if tokens < 1.0:
                raise RateLimitExceededError(
                    f"Rate limit exceeded for user '{context.user_id}' on tool '{tool.name}'. "
                    f"Available tokens: {tokens:.2f}."
                )
                
            self.buckets[key] = (tokens - 1.0, now)
            
    async def reset(self) -> None:
        """Clears all token buckets."""
        async with self.lock:
            self.buckets.clear()
