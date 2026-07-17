"""Google Drive MCP Connector implementation."""
from typing import Any, Dict, List
from mcp.base.connector import MCPConnector
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.base.exceptions import ToolNotFoundError
from mcp.drive.auth import DriveAuth
from mcp.drive.service import DriveService
from mcp.drive.tools import (
    DriveListFilesTool,
    DriveSearchFilesTool,
    DriveReadFileTool,
    DriveDownloadFileTool,
    DriveUploadFileTool,
    DriveCreateFolderTool,
    DriveMoveFileTool,
    DriveDeleteFileTool,
    DriveShareFileTool,
    DriveGetPermissionsTool,
)
from mcp.monitoring.metrics import record_connector_health


class DriveConnector(MCPConnector):
    """Integrates Google Drive storage operations into the MCP framework."""

    def __init__(self, auth: DriveAuth, service: DriveService) -> None:
        self.auth = auth
        self.service = service
        self._tools: Dict[str, MCPTool] = {
            "drive_list_files": DriveListFilesTool(self.service),
            "drive_search_files": DriveSearchFilesTool(self.service),
            "drive_read_file": DriveReadFileTool(self.service),
            "drive_download_file": DriveDownloadFileTool(self.service),
            "drive_upload_file": DriveUploadFileTool(self.service),
            "drive_create_folder": DriveCreateFolderTool(self.service),
            "drive_move_file": DriveMoveFileTool(self.service),
            "drive_delete_file": DriveDeleteFileTool(self.service),
            "drive_share_file": DriveShareFileTool(self.service),
            "drive_get_permissions": DriveGetPermissionsTool(self.service),
        }

    @property
    def name(self) -> str:
        return "drive"

    async def connect(self) -> None:
        """Verifies OAuth credentials validity and health checks connection."""
        await self.auth.get_valid_token()
        is_healthy = await self.health_check()
        if not is_healthy:
            from loguru import logger
            logger.warning("Google Drive connector health check failed.")

    async def disconnect(self) -> None:
        """Closes connection sessions."""
        pass

    async def health_check(self) -> bool:
        """Checks API status by requesting permissions list or similar metadata."""
        try:
            # Simple check against userprofile or files list
            await self.auth.get_valid_token()
            import httpx
            headers = self.auth.get_auth_headers()
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    "https://www.googleapis.com/drive/v3/about?fields=user",
                    headers=headers
                )
            healthy = res.status_code == 200
            record_connector_health(self.name, healthy)
            return healthy
        except Exception:
            record_connector_health(self.name, False)
            return False

    async def refresh_token(self) -> None:
        """Triggers access token refresh."""
        await self.auth.refresh()

    def get_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    async def execute(
        self, tool_name: str, context: MCPContext, params: Dict[str, Any]
    ) -> MCPResult:
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Drive connector does not contain tool '{tool_name}'")
        return await self._tools[tool_name].execute(context, params)
