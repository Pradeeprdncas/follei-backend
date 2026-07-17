"""Outlook integration connector package."""
from mcp.outlook.auth import OutlookAuth
from mcp.outlook.service import OutlookService
from mcp.outlook.connector import OutlookConnector
from mcp.outlook.tools import (
    OutlookSendEmailTool,
    OutlookReplyEmailTool,
    OutlookReadEmailTool,
    OutlookCreateEventTool,
)

__all__ = [
    "OutlookAuth",
    "OutlookService",
    "OutlookConnector",
    "OutlookSendEmailTool",
    "OutlookReplyEmailTool",
    "OutlookReadEmailTool",
    "OutlookCreateEventTool",
]
