"""SSE (Server-Sent Events) Transport for MCP Server."""
import asyncio
import json
import uuid
from typing import Dict, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from loguru import logger
from mcp.base.context import MCPContext
from mcp.server.jsonrpc import JSONRPCRequest, JSONRPCNotification
from mcp.server.router import MCPRequestRouter
from mcp.server.middleware import extract_mcp_context


class SSETransport:
    """Manages active Server-Sent Events connections and maps POST payloads to streams."""

    def __init__(self, router: MCPRequestRouter) -> None:
        self.router = router
        self.api_router = APIRouter()
        # Maps session_id -> asyncio.Queue (stores dictionaries representing events)
        self.sessions: Dict[str, asyncio.Queue] = {}
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.api_router.get("/sse")
        async def handle_sse_connect(request: Request):
            """Establishes persistent SSE event stream for a new client session."""
            session_id = str(uuid.uuid4())
            queue = asyncio.Queue()
            self.sessions[session_id] = queue

            # Immediately inform client of the session endpoint to send HTTP POST requests
            endpoint_url = f"/message?session_id={session_id}"
            await queue.put({"event": "endpoint", "data": endpoint_url})

            logger.info(f"New SSE client connected. Created session '{session_id}'")

            async def event_generator():
                try:
                    while True:
                        event = await queue.get()
                        yield f"event: {event['event']}\ndata: {event['data']}\n\n"
                        queue.task_done()
                except asyncio.CancelledError:
                    logger.info(f"SSE client disconnected. Cleaning up session '{session_id}'")
                finally:
                    self.sessions.pop(session_id, None)

            return StreamingResponse(
                event_generator(),
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable buffering in Nginx reverse proxies
                }
            )

        @self.api_router.post("/message")
        async def handle_mcp_message(
            request: Request,
            session_id: str = Query(..., description="Active client session ID"),
            context: MCPContext = Depends(extract_mcp_context)
        ):
            """Receives JSON-RPC request payloads and routes responses back to client's SSE session."""
            if session_id not in self.sessions:
                raise HTTPException(status_code=400, detail=f"Active SSE Session '{session_id}' not found.")

            try:
                payload = await request.json()
            except Exception:
                logger.error("Failed to parse JSON body from incoming SSE HTTP request.")
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

            # Execute Request
            response = await self.router.dispatch(req_obj, context=context)

            if response is not None:
                # Push the response event through the corresponding SSE session queue
                queue = self.sessions[session_id]
                await queue.put({
                    "event": "message",
                    "data": json.dumps(response)
                })

            # Respond HTTP 202 Accepted to signal message has been queued/processed
            return Response(status_code=202)
