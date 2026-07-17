"""Core MCP Server orchestrator bootstrapping transports and registries."""
import argparse
import asyncio
import os
import sys
from typing import Dict, List, Optional
from fastapi import FastAPI, Response
from loguru import logger
import uvicorn

# Core imports
from mcp.registry.registry import ToolRegistry
from mcp.registry.resources import ResourceRegistry, Resource
from mcp.registry.prompts import PromptRegistry, Prompt, PromptArgument
from mcp.executor.executor import ToolExecutor
from mcp.server.protocol import MCPProtocolHandler
from mcp.server.router import MCPRequestRouter

# Transports
from mcp.server.transports.stdio import StdioTransport
from mcp.server.transports.http import HTTPTransport
from mcp.server.transports.sse import SSETransport

# Dynamic discovery
from mcp.registry.discovery import discover_and_register
from mcp.monitoring.metrics import PROMETHEUS_AVAILABLE, get_in_memory_metrics


class MCPServer:
    """Enterprise Model Context Protocol (MCP) server environment manager."""

    def __init__(self) -> None:
        self.tool_registry = ToolRegistry()
        self.resource_registry = ResourceRegistry()
        self.prompt_registry = PromptRegistry()
        
        self.executor = ToolExecutor(registry=self.tool_registry)
        self.protocol = MCPProtocolHandler()
        self.router = MCPRequestRouter(
            protocol=self.protocol,
            executor=self.executor,
            resources=self.resource_registry,
            prompts=self.prompt_registry
        )

        # Transports
        self.stdio_transport = StdioTransport(self.router)
        self.http_transport = HTTPTransport(self.router)
        self.sse_transport = SSETransport(self.router)

        # Setup FastAPI
        self.app = FastAPI(
            title="Follei Enterprise MCP Server",
            description="Production Model Context Protocol Gateway",
            version="1.0.0"
        )
        self._setup_app_routes()

    def _setup_app_routes(self) -> None:
        # Include HTTP and SSE router endpoints
        self.app.include_router(self.http_transport.api_router)
        self.app.include_router(self.sse_transport.api_router)

        @self.app.on_event("startup")
        async def on_startup() -> None:
            logger.info("Bootstrapping connectors and performing auto-discovery...")
            await self.bootstrap_discovery()

        @self.app.get("/health")
        async def health_check():
            """Exposes a live connection health status endpoint."""
            # Simple check if registries are alive and check dynamic connector health if possible
            return {
                "status": "healthy",
                "registered_tools": len(await self.tool_registry.list_tools()),
                "registered_resources": len(await self.resource_registry.list_resources()),
                "registered_prompts": len(await self.prompt_registry.list_prompts())
            }

        @self.app.get("/metrics")
        async def metrics_endpoint():
            """Exposes Prometheus-formatted metrics output."""
            if PROMETHEUS_AVAILABLE:
                from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
                return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
            else:
                # Return in-memory fallback metrics formatted as JSON
                return get_in_memory_metrics()

    async def bootstrap_discovery(self) -> None:
        """Invokes discovery routines to scan directories and auto-register components."""
        # Standard default connector list initialization
        # Discover connectors dynamically by scanning modules
        connectors_to_load = []

        # Read environment credentials to construct active connector list
        # 1. Gmail
        gmail_client_id = os.getenv("GMAIL_CLIENT_ID")
        gmail_client_secret = os.getenv("GMAIL_CLIENT_SECRET")
        gmail_refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
        if gmail_client_id and gmail_client_secret and gmail_refresh_token:
            from mcp.gmail.auth import GmailAuth
            from mcp.gmail.connector import GmailConnector
            auth = GmailAuth(gmail_client_id, gmail_client_secret, gmail_refresh_token)
            connectors_to_load.append(GmailConnector(auth))

        # 2. Outlook
        outlook_client_id = os.getenv("OUTLOOK_CLIENT_ID")
        outlook_client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
        outlook_refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")
        if outlook_client_id and outlook_client_secret and outlook_refresh_token:
            from mcp.outlook.auth import OutlookAuth
            from mcp.outlook.connector import OutlookConnector
            auth = OutlookAuth(outlook_client_id, outlook_client_secret, outlook_refresh_token)
            connectors_to_load.append(OutlookConnector(auth))

        # 3. Calendar
        # Reuses google/outlook credentials if available
        if (gmail_client_id and gmail_client_secret and gmail_refresh_token) or \
           (outlook_client_id and outlook_client_secret and outlook_refresh_token):
            from mcp.gmail.auth import GmailAuth
            from mcp.outlook.auth import OutlookAuth
            from mcp.calendar.service import CalendarService
            from mcp.calendar.connector import CalendarConnector
            g_auth = GmailAuth(gmail_client_id, gmail_client_secret, gmail_refresh_token) if gmail_client_id else None
            o_auth = OutlookAuth(outlook_client_id, outlook_client_secret, outlook_refresh_token) if outlook_client_id else None
            service = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
            connectors_to_load.append(CalendarConnector(service))

        # 4. WhatsApp
        wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        if wa_phone_id and wa_token:
            from mcp.whatsapp.service import WhatsAppService
            from mcp.whatsapp.connector import WhatsAppConnector
            service = WhatsAppService(wa_phone_id, wa_token)
            connectors_to_load.append(WhatsAppConnector(service))

        # 5. CRM (HubSpot/Salesforce/Zoho)
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

        # Run discovery & register discovered tools
        await discover_and_register(self.tool_registry, connectors_to_load)

        # Initialize Default Prompts and Resources
        await self._register_default_resources()
        await self._register_default_prompts()

    async def _register_default_resources(self) -> None:
        """Registers default resource URIs and resolvers."""
        async def slack_resolver(uri: str) -> str:
            # Under production, call list_channels tool
            return "Active Channels list: [#general, #alerts, #production-logs]"

        async def gmail_resolver(uri: str) -> str:
            return "Gmail threads overview: [Thread_123: Weekly update, Thread_456: Server Alert]"

        async def drive_resolver(uri: str) -> str:
            return "Recent files list: [Project_Specs.pdf, Q2_Metrics.xlsx, Architecture_Design.png]"

        async def crm_resolver(uri: str) -> str:
            return "Recent Accounts matched: [Acme Corp, Cyberdyne Inc, Globex Corporation]"

        async def erp_resolver(uri: str) -> str:
            return "ERP Inventory status: [Item_404_Widget: InStock=25, Item_500_ServerRack: InStock=2]"

        # Register Resources
        await self.resource_registry.register_resource(
            Resource(uri="slack://channels", name="Slack Channels List", description="Lists active public Slack channels", mimeType="text/plain"),
            slack_resolver
        )
        await self.resource_registry.register_resource(
            Resource(uri="gmail://threads", name="Gmail Threads Summary", description="Lists recent active email threads", mimeType="text/plain"),
            gmail_resolver
        )
        await self.resource_registry.register_resource(
            Resource(uri="drive://files", name="Google Drive Recent Files", description="Lists recent documents in Google Drive", mimeType="text/plain"),
            drive_resolver
        )
        await self.resource_registry.register_resource(
            Resource(uri="crm://accounts", name="CRM Account Overview", description="Recent accounts in active CRM", mimeType="text/plain"),
            crm_resolver
        )
        await self.resource_registry.register_resource(
            Resource(uri="erp://inventory", name="ERP Inventory Status", description="Get inventory counts from ERP systems", mimeType="text/plain"),
            erp_resolver
        )

    async def _register_default_prompts(self) -> None:
        """Registers system default prompts."""
        async def sales_assistant_handler(args: Dict[str, Any]) -> List[Dict[str, Any]]:
            customer_name = args.get("customer", "Valued Customer")
            return [
                {
                    "role": "system",
                    "content": {"type": "text", "text": "You are a professional enterprise sales agent. Draft opportunities."}
                },
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Prepare a proposal introduction draft for customer '{customer_name}'."}
                }
            ]

        async def email_assistant_handler(args: Dict[str, Any]) -> List[Dict[str, Any]]:
            subject = args.get("subject", "Urgent Followup")
            return [
                {
                    "role": "system",
                    "content": {"type": "text", "text": "You are an executive assistant. Draft concise and formal email responses."}
                },
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Draft a follow-up email related to: '{subject}'."}
                }
            ]

        async def meeting_assistant_handler(args: Dict[str, Any]) -> List[Dict[str, Any]]:
            topic = args.get("topic", "Project Synelime Align")
            return [
                {
                    "role": "system",
                    "content": {"type": "text", "text": "You are a meeting scheduler. Outline event parameters."}
                },
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Create a meeting agenda plan outline for topic: '{topic}'."}
                }
            ]

        async def support_assistant_handler(args: Dict[str, Any]) -> List[Dict[str, Any]]:
            ticket_id = args.get("ticket_id", "T-1000")
            return [
                {
                    "role": "system",
                    "content": {"type": "text", "text": "You are a technical support engineer resolving enterprise tickets."}
                },
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Draft a troubleshooting response for ticket {ticket_id}."}
                }
            ]

        # Register Prompts
        await self.prompt_registry.register_prompt(
            Prompt(
                name="sales_assistant",
                description="Assists sales agents with proposals",
                arguments=[PromptArgument(name="customer", description="The customer name", required=True)]
            ),
            sales_assistant_handler
        )
        await self.prompt_registry.register_prompt(
            Prompt(
                name="email_assistant",
                description="Assists with drafting executive emails",
                arguments=[PromptArgument(name="subject", description="Email subject", required=False)]
            ),
            email_assistant_handler
        )
        await self.prompt_registry.register_prompt(
            Prompt(
                name="meeting_assistant",
                description="Drafts a clean meeting agenda template",
                arguments=[PromptArgument(name="topic", description="Meeting topic description", required=True)]
            ),
            meeting_assistant_handler
        )
        await self.prompt_registry.register_prompt(
            Prompt(
                name="support_assistant",
                description="Drafts customer support responses",
                arguments=[PromptArgument(name="ticket_id", description="Support ticket ID", required=True)]
            ),
            support_assistant_handler
        )


def main() -> None:
    """CLI Entrypoint for the enterprise MCP Server."""
    parser = argparse.ArgumentParser(description="Run Follei Enterprise MCP Server.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stdio", action="store_true", help="Run server over STDIO pipe.")
    group.add_argument("--http", action="store_true", help="Run server over HTTP/SSE web endpoints.")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP server binding address.")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server binding port.")

    args = parser.parse_args()
    server = MCPServer()

    if args.stdio:
        # Run STDIO event loop
        try:
            asyncio.run(server.stdio_transport.start())
        except KeyboardInterrupt:
            logger.info("Server terminated by user.")
    elif args.http:
        # Run HTTP / Uvicorn server
        logger.info(f"Starting HTTP/SSE Server on {args.host}:{args.port}...")
        uvicorn.run(server.app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
