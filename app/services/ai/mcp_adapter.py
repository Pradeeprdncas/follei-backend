"""MCP Adapter - Integrates MCP server with AI architecture.

The adapter wraps the existing MCP server and exposes it to the AI Planner.
AI Router never communicates directly with MCP.
Only the Planner may request tool execution.

Flow:
AI Router → Planner → MCP Adapter → Existing MCP Server
"""
from typing import Any, Dict, List, Optional
import asyncio
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class MCPAdapter:
    """Adapter for MCP server integration.
    
    Wraps the existing MCP server and provides:
    - Tool execution
    - Tool discovery
    - Tool validation
    - Parallel execution
    - Retry logic
    - Timeout handling
    - Structured logging
    - Metrics
    """
    
    def __init__(self):
        """Initialize MCP adapter."""
        self._mcp_server = None
        self._tool_registry = None
        self._executor = None
        self._initialized = False
        self._metrics = {
            "tool_calls": 0,
            "tool_successes": 0,
            "tool_failures": 0,
            "tool_timeouts": 0,
            "parallel_calls": 0,
        }
    
    async def initialize(self) -> None:
        """Initialize MCP adapter and connect to MCP server."""
        if self._initialized:
            return
        
        try:
            logger.info("Initializing MCP Adapter...")
            
            # Import MCP server components
            from mcp.registry.registry import ToolRegistry
            from mcp.executor.executor import ToolExecutor
            
            # Initialize MCP components
            self._tool_registry = ToolRegistry()
            self._executor = ToolExecutor(registry=self._tool_registry)
            
            # Bootstrap MCP server (connectors, tools, etc.)
            await self._bootstrap_mcp()
            
            self._initialized = True
            logger.info("MCP Adapter initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP Adapter: {e}")
            raise
    
    async def _bootstrap_mcp(self) -> None:
        """Bootstrap MCP server with connectors and tools."""
        try:
            from mcp.registry.discovery import discover_and_register
            import os
            
            connectors_to_load = []
            
            # Check for Gmail credentials
            gmail_client_id = os.getenv("GMAIL_CLIENT_ID")
            gmail_client_secret = os.getenv("GMAIL_CLIENT_SECRET")
            gmail_refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
            if gmail_client_id and gmail_client_secret and gmail_refresh_token:
                from mcp.gmail.auth import GmailAuth
                from mcp.gmail.connector import GmailConnector
                auth = GmailAuth(gmail_client_id, gmail_client_secret, gmail_refresh_token)
                connectors_to_load.append(GmailConnector(auth))
            
            # Check for Outlook credentials
            outlook_client_id = os.getenv("OUTLOOK_CLIENT_ID")
            outlook_client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
            outlook_refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")
            if outlook_client_id and outlook_client_secret and outlook_refresh_token:
                from mcp.outlook.auth import OutlookAuth
                from mcp.outlook.connector import OutlookConnector
                auth = OutlookAuth(outlook_client_id, outlook_client_secret, outlook_refresh_token)
                connectors_to_load.append(OutlookConnector(auth))
            
            # Check for WhatsApp credentials
            wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
            wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
            if wa_phone_id and wa_token:
                from mcp.whatsapp.service import WhatsAppService
                from mcp.whatsapp.connector import WhatsAppConnector
                service = WhatsAppService(wa_phone_id, wa_token)
                connectors_to_load.append(WhatsAppConnector(service))
            
            # Check for CRM credentials
            crm_provider = os.getenv("CRM_PROVIDER")
            if crm_provider:
                from mcp.crm.service import CRMService
                from mcp.crm.connector import CRMConnector
                credentials = {}
                if crm_provider == "hubspot":
                    credentials["api_key"] = os.getenv("HUBSPOT_API_KEY")
                elif crm_provider == "salesforce":
                    credentials["instance_url"] = os.getenv("SALESFORCE_INSTANCE_URL")
                    credentials["access_token"] = os.getenv("SALESFORCE_ACCESS_TOKEN")
                elif crm_provider == "zoho":
                    credentials["access_token"] = os.getenv("ZOHO_ACCESS_TOKEN")
                    credentials["base_url"] = os.getenv("ZOHO_BASE_URL", "https://www.zohoapis.com/crm/v2")
                
                if credentials:
                    service = CRMService(provider=crm_provider, credentials=credentials)
                    connectors_to_load.append(CRMConnector(service))
            
            # Discover and register tools
            await discover_and_register(self._tool_registry, connectors_to_load)
            
            logger.info(f"MCP bootstrapped with {len(connectors_to_load)} connectors")
            
        except Exception as e:
            logger.warning(f"MCP bootstrap failed (some tools may not be available): {e}")
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None,
        timeout: float = 30.0,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """Execute a single MCP tool.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Execution context (user_id, tenant_id, etc.)
            timeout: Timeout in seconds
            max_retries: Maximum number of retries
            
        Returns:
            Tool execution result
        """
        if not self._initialized:
            await self.initialize()
        
        context = context or {}
        self._metrics["tool_calls"] += 1
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Executing MCP tool: {tool_name} (attempt {attempt + 1}/{max_retries + 1})")
                
                # Create MCP context
                from mcp.base.context import MCPContext
                mcp_context = MCPContext(
                    user_id=context.get("user_id"),
                    tenant_id=context.get("tenant_id"),
                    session_id=context.get("session_id"),
                    parameters=parameters
                )
                
                # Execute tool with timeout
                result = await asyncio.wait_for(
                    self._executor.execute(tool_name, mcp_context, parameters),
                    timeout=timeout
                )
                
                self._metrics["tool_successes"] += 1
                logger.info(f"Tool {tool_name} executed successfully")
                
                return {
                    "success": True,
                    "tool": tool_name,
                    "result": result,
                    "attempt": attempt + 1
                }
                
            except asyncio.TimeoutError:
                self._metrics["tool_timeouts"] += 1
                logger.warning(f"Tool {tool_name} timed out (attempt {attempt + 1})")
                
                if attempt == max_retries:
                    return {
                        "success": False,
                        "tool": tool_name,
                        "error": "timeout",
                        "message": f"Tool execution timed out after {timeout}s",
                        "attempt": attempt + 1
                    }
            
            except Exception as e:
                logger.error(f"Tool {tool_name} failed (attempt {attempt + 1}): {e}")
                
                if attempt == max_retries:
                    self._metrics["tool_failures"] += 1
                    return {
                        "success": False,
                        "tool": tool_name,
                        "error": "execution_error",
                        "message": str(e),
                        "attempt": attempt + 1
                    }
                
                # Wait before retry
                await asyncio.sleep(0.5 * (attempt + 1))
    
    async def execute_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Dict[str, Any] = None,
        timeout: float = 60.0
    ) -> List[Dict[str, Any]]:
        """Execute multiple MCP tools in parallel.
        
        Args:
            tool_calls: List of dicts with 'tool_name' and 'parameters'
            context: Execution context
            timeout: Total timeout in seconds
            
        Returns:
            List of execution results
        """
        if not self._initialized:
            await self.initialize()
        
        context = context or {}
        self._metrics["parallel_calls"] += 1
        
        logger.info(f"Executing {len(tool_calls)} MCP tools in parallel")
        
        # Create tasks
        tasks = []
        for call in tool_calls:
            task = self.execute_tool(
                tool_name=call["tool_name"],
                parameters=call.get("parameters", {}),
                context=context,
                timeout=call.get("timeout", 30.0),
                max_retries=call.get("max_retries", 2)
            )
            tasks.append(task)
        
        # Execute in parallel with overall timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "success": False,
                        "tool": tool_calls[i]["tool_name"],
                        "error": "exception",
                        "message": str(result)
                    })
                else:
                    processed_results.append(result)
            
            logger.info(f"Parallel execution complete: {len(processed_results)} results")
            return processed_results
            
        except asyncio.TimeoutError:
            logger.error(f"Parallel execution timed out after {timeout}s")
            return [
                {
                    "success": False,
                    "tool": call["tool_name"],
                    "error": "timeout",
                    "message": f"Parallel execution timed out after {timeout}s"
                }
                for call in tool_calls
            ]
    
    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available MCP tools.
        
        Returns:
            List of available tools with schemas
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            tools = await self._tool_registry.list_tools()
            
            # Format tools
            formatted_tools = []
            for tool in tools:
                formatted_tools.append({
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "parameters": tool.get("inputSchema", {}),
                    "category": self._categorize_tool(tool.get("name", ""))
                })
            
            logger.info(f"Discovered {len(formatted_tools)} MCP tools")
            return formatted_tools
            
        except Exception as e:
            logger.error(f"Tool discovery failed: {e}")
            return []
    
    async def validate_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool parameters before execution.
        
        Args:
            tool_name: Name of the tool
            parameters: Parameters to validate
            
        Returns:
            Validation result
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get tool schema
            tools = await self._tool_registry.list_tools()
            tool_schema = next((t for t in tools if t.get("name") == tool_name), None)
            
            if not tool_schema:
                return {
                    "valid": False,
                    "error": f"Tool {tool_name} not found"
                }
            
            # Validate parameters against schema
            schema = tool_schema.get("inputSchema", {})
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            
            # Check required parameters
            missing = [param for param in required if param not in parameters]
            if missing:
                return {
                    "valid": False,
                    "error": f"Missing required parameters: {missing}"
                }
            
            # Check parameter types
            for param, value in parameters.items():
                if param in properties:
                    expected_type = properties[param].get("type")
                    if expected_type and not isinstance(value, self._get_python_type(expected_type)):
                        return {
                            "valid": False,
                            "error": f"Parameter {param} should be {expected_type}"
                        }
            
            return {
                "valid": True,
                "tool": tool_name,
                "parameters": parameters
            }
            
        except Exception as e:
            logger.error(f"Tool validation failed: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool schema or None
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            tools = await self._tool_registry.list_tools()
            tool = next((t for t in tools if t.get("name") == tool_name), None)
            
            if tool:
                return {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "inputSchema": tool.get("inputSchema", {}),
                    "outputSchema": tool.get("outputSchema", {})
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get tool schema: {e}")
            return None
    
    def _categorize_tool(self, tool_name: str) -> str:
        """Categorize tool by name.
        
        Args:
            tool_name: Tool name
            
        Returns:
            Tool category
        """
        name_lower = tool_name.lower()
        
        if any(keyword in name_lower for keyword in ["email", "gmail", "outlook", "send"]):
            return "communication"
        elif any(keyword in name_lower for keyword in ["calendar", "event", "schedule"]):
            return "calendar"
        elif any(keyword in name_lower for keyword in ["crm", "contact", "lead", "opportunity"]):
            return "crm"
        elif any(keyword in name_lower for keyword in ["whatsapp", "message", "chat"]):
            return "messaging"
        elif any(keyword in name_lower for keyword in ["drive", "file", "document"]):
            return "storage"
        elif any(keyword in name_lower for keyword in ["erp", "inventory", "order"]):
            return "erp"
        else:
            return "general"
    
    def _get_python_type(self, json_type: str) -> type:
        """Convert JSON schema type to Python type.
        
        Args:
            json_type: JSON schema type
            
        Returns:
            Python type
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        return type_map.get(json_type, str)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get MCP adapter metrics.
        
        Returns:
            Metrics dictionary
        """
        return {
            **self._metrics,
            "initialized": self._initialized,
            "available_tools": len(self._tool_registry.list_tools()) if self._tool_registry else 0
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check MCP adapter health.
        
        Returns:
            Health status
        """
        try:
            tools = await self.discover_tools()
            return {
                "status": "healthy",
                "tools_available": len(tools),
                "initialized": self._initialized
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "initialized": self._initialized
            }


# Singleton instance
_mcp_adapter = None


def get_mcp_adapter() -> MCPAdapter:
    """Get or create the singleton MCP Adapter.
    
    Returns:
        MCPAdapter instance
    """
    global _mcp_adapter
    if _mcp_adapter is None:
        _mcp_adapter = MCPAdapter()
    return _mcp_adapter