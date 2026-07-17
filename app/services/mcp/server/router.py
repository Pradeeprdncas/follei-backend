"""MCP Server JSON-RPC request router and method dispatcher."""
from typing import Any, Dict, Optional, Union
from loguru import logger
from mcp.base.context import MCPContext
from mcp.base.exceptions import MCPException
from mcp.executor.executor import ToolExecutor
from mcp.registry.resources import ResourceRegistry
from mcp.registry.prompts import PromptRegistry
from mcp.server.jsonrpc import (
    JSONRPCRequest,
    JSONRPCNotification,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    make_error_response,
    make_success_response,
)
from mcp.server.protocol import MCPProtocolHandler, ProtocolError


class MCPRequestRouter:
    """Dispatches validated JSON-RPC requests to appropriate backend services."""

    def __init__(
        self,
        protocol: MCPProtocolHandler,
        executor: ToolExecutor,
        resources: ResourceRegistry,
        prompts: PromptRegistry,
    ) -> None:
        self.protocol = protocol
        self.executor = executor
        self.resources = resources
        self.prompts = prompts

    async def dispatch(
        self, request: Union[JSONRPCRequest, JSONRPCNotification], context: Optional[MCPContext] = None
    ) -> Optional[Dict[str, Any]]:
        """Routes the incoming JSON-RPC payload and returns a response dictionary (or None)."""
        is_notification = isinstance(request, JSONRPCNotification)
        req_id = None if is_notification else request.id

        try:
            # 1. State/Lifecycle Validation
            self.protocol.validate_request(request.method)

            # 2. Dispatch to dedicated handler
            method = request.method
            params = request.params or {}

            if method == "initialize":
                res = self.protocol.handle_initialize(params)
                return make_success_response(res, req_id)

            elif method == "notifications/initialized":
                self.protocol.handle_initialized_notification()
                return None  # Notifications do not return responses

            elif method == "tools/list":
                tools = await self.executor.registry.list_tools()
                tools_list = []
                for t in tools:
                    tools_list.append({
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema
                    })
                return make_success_response({"tools": tools_list}, req_id)

            elif method == "tools/call":
                if "name" not in params:
                    return make_error_response(INVALID_PARAMS, "Missing 'name' in tools/call parameters.", req_id)
                
                tool_name = params["name"]
                tool_args = params.get("arguments", {})

                # Generate or forward execution context
                if not context:
                    context = MCPContext(
                        organization_id="org_default",
                        user_id="user_default",
                        agent_id="agent_default",
                        permissions=["*"],
                        request_id=f"req_{req_id or 'notif'}",
                        trace_id="trace_default"
                    )

                logger.info(f"Routing tools/call for tool '{tool_name}'...")
                exec_result = await self.executor.execute(tool_name, context, tool_args)

                if exec_result.success:
                    # Return formatted content back to MCP Client
                    # Content lists must match MCP specifications
                    data = exec_result.data
                    text_content = str(data) if data is not None else ""
                    return make_success_response({
                        "content": [{"type": "text", "text": text_content}]
                    }, req_id)
                    
                else:
                    # Tool executed but returned success=False (e.g. error returned from API)
                    return make_success_response({
                        "content": [{"type": "text", "text": exec_result.error or "Unknown tool execution failure"}],
                        "isError": True
                    }, req_id)

            elif method == "resources/list":
                res_items = await self.resources.list_resources()
                res_list = []
                for r in res_items:
                    res_list.append({
                        "uri": r.uri,
                        "name": r.name,
                        "description": r.description,
                        "mimeType": r.mimeType
                    })
                return make_success_response({"resources": res_list}, req_id)

            elif method == "resources/read":
                if "uri" not in params:
                    return make_error_response(INVALID_PARAMS, "Missing 'uri' parameter in resources/read.", req_id)
                uri = params["uri"]
                try:
                    content = await self.resources.read_resource(uri)
                    # Deduce basic mimeType from registered resources if possible
                    registered = await self.resources.list_resources()
                    mime_type = "text/plain"
                    for r in registered:
                        if r.uri == uri and r.mimeType:
                            mime_type = r.mimeType
                            break

                    return make_success_response({
                        "contents": [{
                            "uri": uri,
                            "mimeType": mime_type,
                            "text": content
                        }]
                    }, req_id)
                except KeyError as e:
                    return make_error_response(INVALID_PARAMS, str(e), req_id)

            elif method == "prompts/list":
                prompts = await self.prompts.list_prompts()
                prompts_list = []
                for p in prompts:
                    prompts_list.append({
                        "name": p.name,
                        "description": p.description,
                        "arguments": [
                            {"name": arg.name, "description": arg.description, "required": arg.required}
                            for arg in p.arguments
                        ]
                    })
                return make_success_response({"prompts": prompts_list}, req_id)

            elif method == "prompts/get":
                if "name" not in params:
                    return make_error_response(INVALID_PARAMS, "Missing 'name' parameter in prompts/get.", req_id)
                prompt_name = params["name"]
                prompt_args = params.get("arguments", {})
                try:
                    messages = await self.prompts.get_prompt(prompt_name, prompt_args)
                    return make_success_response({
                        "description": f"Rendered prompt {prompt_name}",
                        "messages": messages
                    }, req_id)
                except KeyError as e:
                    return make_error_response(INVALID_PARAMS, str(e), req_id)

            else:
                if is_notification:
                    logger.warning(f"Unhandled notification method: {method}")
                    return None
                return make_error_response(METHOD_NOT_FOUND, f"Method '{method}' not found.", req_id)

        except ProtocolError as e:
            logger.error(f"MCP Protocol lifecycle violation: {e}")
            if is_notification:
                return None
            return make_error_response(INVALID_REQUEST, str(e), req_id)
        except MCPException as e:
            logger.exception(f"MCP tool validation failure: {e}")
            if is_notification:
                return None
            return make_error_response(INVALID_PARAMS, str(e), req_id)
        except Exception as e:
            logger.exception(f"Unexpected internal server error routing request: {e}")
            if is_notification:
                return None
            return make_error_response(INTERNAL_ERROR, f"Internal routing error: {str(e)}", req_id)
