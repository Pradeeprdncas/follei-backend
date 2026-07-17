"""Gmail integration connector package."""
from mcp.gmail.auth import GmailAuth
from mcp.gmail.service import GmailService
from mcp.gmail.connector import GmailConnector
from mcp.gmail.tools import (
    GmailSendEmailTool,
    GmailReplyEmailTool,
    GmailSearchEmailTool,
    GmailReadThreadTool,
)

__all__ = [
    "GmailAuth",
    "GmailService",
    "GmailConnector",
    "GmailSendEmailTool",
    "GmailReplyEmailTool",
    "GmailSearchEmailTool",
    "GmailReadThreadTool",
]
