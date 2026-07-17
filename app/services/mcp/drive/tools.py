"""Google Drive MCP tool implementations."""
from typing import Any, Dict
from mcp.base.capability import MCPCapability
from mcp.base.context import MCPContext
from mcp.base.result import MCPResult
from mcp.base.tool import MCPTool
from mcp.drive.service import DriveService
from mcp.drive.schemas import (
    LIST_FILES_SCHEMA,
    SEARCH_FILES_SCHEMA,
    READ_FILE_SCHEMA,
    DOWNLOAD_FILE_SCHEMA,
    UPLOAD_FILE_SCHEMA,
    CREATE_FOLDER_SCHEMA,
    MOVE_FILE_SCHEMA,
    DELETE_FILE_SCHEMA,
    SHARE_FILE_SCHEMA,
    GET_PERMISSIONS_SCHEMA,
)


class DriveListFilesTool(MCPTool):
    """Lists files."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_list_files"

    @property
    def description(self) -> str:
        return "Lists files and metadata stored in the user's Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return LIST_FILES_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.list_files(
                page_size=params.get("page_size", 20)
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveSearchFilesTool(MCPTool):
    """Searches files."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_search_files"

    @property
    def description(self) -> str:
        return "Searches files matching criteria in Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SEARCH_FILES_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.search_files(
                query=params["query"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveReadFileTool(MCPTool):
    """Reads file content."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_read_file"

    @property
    def description(self) -> str:
        return "Reads the text contents of a document in Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return READ_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "string"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.read_file(
                file_id=params["file_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveDownloadFileTool(MCPTool):
    """Downloads file details."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_download_file"

    @property
    def description(self) -> str:
        return "Downloads file content and retrieves sizing/preview metrics."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return DOWNLOAD_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.download_file(
                file_id=params["file_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveUploadFileTool(MCPTool):
    """Uploads file content."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_upload_file"

    @property
    def description(self) -> str:
        return "Uploads a text/data file snippet into Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return UPLOAD_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.upload_file(
                name=params["name"],
                content=params["content"],
                mime_type=params.get("mime_type", "text/plain"),
                parent_id=params.get("parent_id")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveCreateFolderTool(MCPTool):
    """Creates folder."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_create_folder"

    @property
    def description(self) -> str:
        return "Creates a new folder directory in Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return CREATE_FOLDER_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.create_folder(
                name=params["name"],
                parent_id=params.get("parent_id")
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveMoveFileTool(MCPTool):
    """Moves file parent."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_move_file"

    @property
    def description(self) -> str:
        return "Moves a file between folders in Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return MOVE_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.move_file(
                file_id=params["file_id"],
                add_parents=params["add_parents"],
                remove_parents=params["remove_parents"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveDeleteFileTool(MCPTool):
    """Trashes or deletes file."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_delete_file"

    @property
    def description(self) -> str:
        return "Trashes a file or deletes it permanently from Google Drive."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return DELETE_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.delete_file(
                file_id=params["file_id"],
                trash=params.get("trash", True)
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveShareFileTool(MCPTool):
    """Shares permissions."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_share_file"

    @property
    def description(self) -> str:
        return "Grants access permissions on a Google Drive file to an email address."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return SHARE_FILE_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.share_file(
                file_id=params["file_id"],
                email_address=params["email_address"],
                role=params["role"],
                type_val=params["type"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))


class DriveGetPermissionsTool(MCPTool):
    """Lists permissions."""

    def __init__(self, service: DriveService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return "drive_get_permissions"

    @property
    def description(self) -> str:
        return "Lists permissions and access controls currently set on a Google Drive file."

    @property
    def capability(self) -> MCPCapability:
        return MCPCapability.STORAGE

    @property
    def input_schema(self) -> Dict[str, Any]:
        return GET_PERMISSIONS_SCHEMA

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {"type": "array", "items": {"type": "object"}}

    async def execute(self, context: MCPContext, params: Dict[str, Any]) -> MCPResult:
        try:
            res = await self.service.get_permissions(
                file_id=params["file_id"]
            )
            return MCPResult(success=True, data=res)
        except Exception as e:
            return MCPResult(success=False, error=str(e))
