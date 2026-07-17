"""Asynchronous STDIO Transport for MCP Server."""
import asyncio
import json
import sys
from typing import Optional
from loguru import logger
from mcp.server.jsonrpc import JSONRPCRequest, JSONRPCNotification
from mcp.server.router import MCPRequestRouter


class StdioTransport:
    """Listens for JSON-RPC messages on stdin and writes responses to stdout."""

    def __init__(self, router: MCPRequestRouter) -> None:
        self.router = router
        self._running = False
        self._read_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts the asynchronous reading and processing loop."""
        # 1. Reconfigure logging to write strictly to stderr
        # Since stdout is reserved for JSON-RPC messages, any prints/logs on stdout will corrupt the connection
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        
        # Override default print to write to stderr
        sys.stdout = sys.stderr

        self._running = True
        logger.info("Starting STDIO transport. Listening for JSON-RPC messages on stdin...")
        self._read_task = asyncio.create_task(self._read_loop())
        await self._read_task

    async def stop(self) -> None:
        """Stops the transport loop."""
        self._running = False
        if self._read_task:
            self._read_task.cancel()
        logger.info("STDIO transport stopped.")

    async def _read_loop(self) -> None:
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        # Retrieve a direct non-redirected reference to actual stdout to print frames back to client
        # Since we redirected sys.stdout to sys.stderr, we fetch the underlying original sys.__stdout__ stream
        stdout_stream = sys.__stdout__

        while self._running:
            try:
                line_bytes = await reader.readline()
                if not line_bytes:
                    # End of file / pipe closed
                    logger.info("Input pipe closed (EOF). Stopping STDIO transport...")
                    break

                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue

                logger.debug(f"Received stdio message: {line}")
                
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.error("JSON parsing error on incoming line.")
                    err_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
                        "id": None
                    }
                    stdout_stream.write(json.dumps(err_response) + "\n")
                    stdout_stream.flush()
                    continue

                # Parse JSON-RPC 2.0 object
                try:
                    if "id" in payload:
                        req_obj = JSONRPCRequest.model_validate(payload)
                    else:
                        req_obj = JSONRPCNotification.model_validate(payload)
                except Exception as e:
                    logger.error(f"Payload validation failed: {e}")
                    err_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": f"Invalid request: {str(e)}"},
                        "id": payload.get("id")
                    }
                    stdout_stream.write(json.dumps(err_response) + "\n")
                    stdout_stream.flush()
                    continue

                # Dispatch
                response = await self.router.dispatch(req_obj)
                
                if response is not None:
                    # Notifications do not produce responses, requests do
                    response_json = json.dumps(response)
                    logger.debug(f"Sending stdio response: {response_json}")
                    stdout_stream.write(response_json + "\n")
                    stdout_stream.flush()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unhandled error in STDIO read loop: {e}")
