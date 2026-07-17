"""MCP Prompt Registry implementation."""
import asyncio
from typing import Any, Callable, Dict, List, Optional, Awaitable
from pydantic import BaseModel


class PromptArgument(BaseModel):
    """Pydantic model representing a prompt input argument."""
    name: str
    description: Optional[str] = None
    required: bool = False


class Prompt(BaseModel):
    """Pydantic model representing a discoverable MCP Prompt template."""
    name: str
    description: Optional[str] = None
    arguments: List[PromptArgument] = []


# Render handler takes arguments dict and returns structured messages
PromptRenderHandler = Callable[[Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]


class PromptRegistry:
    """Thread-safe registry for MCP Prompt templates and rendering handlers."""

    def __init__(self) -> None:
        self._prompts: Dict[str, Prompt] = {}
        self._handlers: Dict[str, PromptRenderHandler] = {}
        self._lock = asyncio.Lock()

    async def register_prompt(
        self, prompt: Prompt, handler: PromptRenderHandler
    ) -> None:
        """Registers a prompt template along with its prompt render handler."""
        async with self._lock:
            self._prompts[prompt.name] = prompt
            self._handlers[prompt.name] = handler

    async def unregister_prompt(self, name: str) -> None:
        """Deregisters a prompt by name."""
        async with self._lock:
            self._prompts.pop(name, None)
            self._handlers.pop(name, None)

    async def list_prompts(self) -> List[Prompt]:
        """Lists all registered prompts."""
        async with self._lock:
            return list(self._prompts.values())

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Renders prompt messages by name with provided arguments."""
        async with self._lock:
            if name not in self._handlers:
                raise KeyError(f"Prompt '{name}' is not registered.")
            handler = self._handlers[name]
        
        # Invoke handler outside lock
        return await handler(arguments)
