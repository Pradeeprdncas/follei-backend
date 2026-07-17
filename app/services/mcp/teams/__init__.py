"""Microsoft Teams MCP connector package."""
from mcp.teams.connector import TeamsConnector
from mcp.teams.service import TeamsService
from mcp.teams.auth import TeamsAuth

__all__ = ["TeamsConnector", "TeamsService", "TeamsAuth"]
