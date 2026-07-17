"""MCP Connector and Tool Auto-Discovery module."""
import importlib
import os
import inspect
from typing import List, Optional, Type
from loguru import logger
from mcp.base.connector import MCPConnector
from mcp.registry.registry import ToolRegistry


async def discover_and_register(
    registry: ToolRegistry, connectors_list: List[MCPConnector] = None
) -> List[MCPConnector]:
    """Discovers tools by connecting loaded connectors and registering their tools.

    If connectors_list is not provided, dynamically scans mcp/* subdirectories
    to find, import, and instantiate connector classes.
    """
    if connectors_list is None:
        connectors_list = []
        # Get directory of the mcp folder
        mcp_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logger.info(f"Scanning '{mcp_dir}' for connectors...")

        # List subdirectories
        for entry in os.listdir(mcp_dir):
            sub_path = os.path.join(mcp_dir, entry)
            if not os.path.isdir(sub_path):
                continue
            
            # Skip core framework internal folders
            if entry in ("base", "registry", "executor", "monitoring", "server", "tests", "__pycache__"):
                continue

            # Try to discover a connector in the subfolder
            try:
                connector_module_name = f"mcp.{entry}.connector"
                # Check if connector.py exists
                if os.path.exists(os.path.join(sub_path, "connector.py")):
                    module = importlib.import_module(connector_module_name)
                    
                    # Find class subclassing MCPConnector
                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, MCPConnector)
                            and obj is not MCPConnector
                        ):
                            logger.info(f"Discovered connector class '{obj.__name__}' in package '{entry}'")
                            
                            # Attempt to instantiate using environment variables
                            instantiated = _instantiate_connector_from_env(entry, obj)
                            if instantiated:
                                connectors_list.append(instantiated)
            except Exception as e:
                logger.error(f"Failed during dynamic discovery scanning of '{entry}': {e}")

    # Register each discovered connector
    for connector in connectors_list:
        try:
            logger.info(f"Connecting to connector: {connector.name}...")
            await connector.connect()
            
            # Retrieve tools from connector
            tools = connector.get_tools()
            logger.info(f"Discovered {len(tools)} tools from {connector.name}")
            
            for tool in tools:
                await registry.register_tool(tool)
                logger.debug(f"Registered tool: {tool.name} (capability: {tool.capability.value})")
        except Exception as e:
            logger.exception(f"Failed to load tools from connector '{connector.name}': {e}")

    return connectors_list


def _instantiate_connector_from_env(name: str, cls: Type[MCPConnector]) -> Optional[MCPConnector]:
    """Helper factory that creates connector instances using environment variables."""
    try:
        if name == "gmail":
            client_id = os.getenv("GMAIL_CLIENT_ID")
            client_secret = os.getenv("GMAIL_CLIENT_SECRET")
            refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
            if client_id and client_secret and refresh_token:
                from mcp.gmail.auth import GmailAuth
                auth = GmailAuth(client_id, client_secret, refresh_token)
                return cls(auth)

        elif name == "outlook":
            client_id = os.getenv("OUTLOOK_CLIENT_ID")
            client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
            refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")
            if client_id and client_secret and refresh_token:
                from mcp.outlook.auth import OutlookAuth
                auth = OutlookAuth(client_id, client_secret, refresh_token)
                return cls(auth)

        elif name == "calendar":
            gmail_client_id = os.getenv("GMAIL_CLIENT_ID")
            gmail_refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
            outlook_client_id = os.getenv("OUTLOOK_CLIENT_ID")
            outlook_refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")
            
            # Reuses google/outlook credentials
            if gmail_client_id or outlook_client_id:
                from mcp.gmail.auth import GmailAuth
                from mcp.outlook.auth import OutlookAuth
                from mcp.calendar.service import CalendarService
                g_auth = GmailAuth(gmail_client_id, os.getenv("GMAIL_CLIENT_SECRET", ""), gmail_refresh_token) if gmail_client_id else None
                o_auth = OutlookAuth(outlook_client_id, os.getenv("OUTLOOK_CLIENT_SECRET", ""), outlook_refresh_token) if outlook_client_id else None
                service = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
                return cls(service)

        elif name == "whatsapp":
            phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
            token = os.getenv("WHATSAPP_ACCESS_TOKEN")
            if phone_id and token:
                from mcp.whatsapp.service import WhatsAppService
                service = WhatsAppService(phone_id, token)
                return cls(service)

        elif name == "slack":
            token = os.getenv("SLACK_BOT_TOKEN")
            if token:
                from mcp.slack.service import SlackService
                service = SlackService(token=token)
                return cls(service)

        elif name == "drive":
            client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
            client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
            refresh_token = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN") or os.getenv("GMAIL_REFRESH_TOKEN")
            if client_id and client_secret and refresh_token:
                from mcp.drive.auth import DriveAuth
                from mcp.drive.service import DriveService
                auth = DriveAuth(client_id, client_secret, refresh_token)
                service = DriveService(auth)
                return cls(auth=auth, service=service)

        elif name == "teams":
            client_id = os.getenv("MS_TEAMS_CLIENT_ID") or os.getenv("OUTLOOK_CLIENT_ID")
            client_secret = os.getenv("MS_TEAMS_CLIENT_SECRET") or os.getenv("OUTLOOK_CLIENT_SECRET")
            refresh_token = os.getenv("MS_TEAMS_REFRESH_TOKEN") or os.getenv("OUTLOOK_REFRESH_TOKEN")
            if client_id and client_secret and refresh_token:
                from mcp.teams.auth import TeamsAuth
                from mcp.teams.service import TeamsService
                auth = TeamsAuth(client_id, client_secret, refresh_token)
                service = TeamsService(auth)
                return cls(auth=auth, service=service)

        elif name == "erp":
            provider = os.getenv("ERP_PROVIDER")
            if provider:
                from mcp.erp.service import ERPService
                credentials = {}
                if provider == "sap":
                    credentials["base_url"] = os.getenv("SAP_BASE_URL")
                    credentials["username"] = os.getenv("SAP_USERNAME")
                    credentials["password"] = os.getenv("SAP_PASSWORD")
                elif provider == "oracle":
                    credentials["base_url"] = os.getenv("ORACLE_BASE_URL")
                    credentials["client_id"] = os.getenv("ORACLE_CLIENT_ID")
                    credentials["client_secret"] = os.getenv("ORACLE_CLIENT_SECRET")
                elif provider == "odoo":
                    credentials["url"] = os.getenv("ODOO_URL")
                    credentials["db"] = os.getenv("ODOO_DB")
                    credentials["username"] = os.getenv("ODOO_USERNAME")
                    credentials["password"] = os.getenv("ODOO_PASSWORD")
                elif provider == "dynamics":
                    credentials["resource"] = os.getenv("DYNAMICS_RESOURCE")
                    credentials["client_id"] = os.getenv("DYNAMICS_CLIENT_ID")
                    credentials["client_secret"] = os.getenv("DYNAMICS_CLIENT_SECRET")

                if credentials:
                    service = ERPService(provider=provider, credentials=credentials)
                    return cls(service)

    except Exception as e:
        logger.error(f"Failed to instantiate connector '{name}' from env variables: {e}")
    return None
