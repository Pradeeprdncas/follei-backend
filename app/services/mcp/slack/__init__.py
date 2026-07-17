"""Slack MCP connector package."""
from mcp.slack.connector import SlackConnector
from mcp.slack.service import SlackService
from mcp.slack.auth import SlackAuth

__all__ = ["SlackConnector", "SlackService", "SlackAuth"]
