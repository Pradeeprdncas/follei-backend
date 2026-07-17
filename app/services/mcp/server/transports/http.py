"""HTTP POST Transport wrapper for MCP Server."""
from fastapi import APIRouter, Depends, Request, Response
from loguru import logger
from mcp.base.context import MCPContext
from mcp.server.jsonrpc import JSONRPCRequest, JSONRPCNotification
from mcp.server.router import MCPRequestRouter
from mcp.server.middleware import extract_mcp_context


class HTTPTransport:
    """Provides HTTP POST endpoint mapping to route single JSON-RPC operations."""

    def __init__(self, router: MCPRequestRouter) -> None:
        self.router = router
        self.api_router = APIRouter()
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.api_router.post("/mcp")
        async def handle_mcp_request(
            request: Request,
            context: MCPContext = Depends(extract_mcp_context)
        ):
            """Core endpoint receiving JSON-RPC requests via POST."""
            try:
                payload = await request.json()
            except Exception:
                logger.error("Failed to parse JSON body from incoming HTTP request.")
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
                    "id": None
                }

            # Parse request or notification
            try:
                if "id" in payload:
                    req_obj = JSONRPCRequest.model_validate(payload)
                else:
                    req_obj = JSONRPCNotification.model_validate(payload)
            except Exception as e:
                logger.error(f"Payload validation failed: {e}")
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": f"Invalid request: {str(e)}"},
                    "id": payload.get("id")
                }

            # Dispatch request
            response = await self.router.dispatch(req_obj, context=context)
            if response is None:
                # Notifications return 204 No Content
                return Response(status_code=204)
            return response
