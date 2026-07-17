"""MCP Resource Registry implementation."""
import asyncio
from typing import Any, Callable, Dict, List, Optional, Awaitable
from pydantic import BaseModel


class Resource(BaseModel):
    """Pydantic model representing a discoverable MCP Resource."""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


# A handler is an async function taking URI and returning string content
ResourceReadHandler = Callable[[str], Awaitable[str]]


class ResourceRegistry:
    """Thread-safe registry for MCP Resources and their read resolvers."""

    def __init__(self) -> None:
        self._resources: Dict[str, Resource] = {}
        self._handlers: Dict[str, ResourceReadHandler] = {}
        self._lock = asyncio.Lock()

    async def register_resource(
        self, resource: Resource, handler: ResourceReadHandler
    ) -> None:
        """Registers a resource along with its async content read handler."""
        async with self._lock:
            self._resources[resource.uri] = resource
            self._handlers[resource.uri] = handler

    async def unregister_resource(self, uri: str) -> None:
        """Deregisters a resource by URI."""
        async with self._lock:
            self._resources.pop(uri, None)
            self._handlers.pop(uri, None)

    async def list_resources(self) -> List[Resource]:
        """Lists all registered resources."""
        async with self._lock:
            return list(self._resources.values())

    async def read_resource(self, uri: str) -> str:
        """Reads content from a registered resource using its handler."""
        async with self._lock:
            if uri not in self._handlers:
                raise KeyError(f"Resource with URI '{uri}' is not registered.")
            handler = self._handlers[uri]
        
        # Invoke the handler outside of lock for concurrency
        return await handler(uri)
