"""Google Drive REST service wrapper using HTTPX."""
import json
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from mcp.base.exceptions import ConnectorError, ExecutionError
from mcp.drive.auth import DriveAuth


class DriveService:
    """Wrapper for calling Google Drive API v3 REST endpoints using HTTPX and DriveAuth."""

    def __init__(self, auth: DriveAuth) -> None:
        self.auth = auth
        self.base_url = "https://www.googleapis.com/drive/v3"
        self.upload_url = "https://www.googleapis.com/upload/drive/v3"

    async def _get_headers(self) -> Dict[str, str]:
        access_token = await self.auth.get_valid_token()
        headers = self.auth.get_auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    async def list_files(self, page_size: int = 20) -> List[Dict[str, Any]]:
        """Lists files in the user's Google Drive."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files"
        params = {"pageSize": page_size, "fields": "files(id, name, mimeType, parents)"}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers, params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Drive list_files failed ({res.status_code}): {res.text}")
            return res.json().get("files", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to list Drive files: {e}") from e

    async def search_files(self, query: str) -> List[Dict[str, Any]]:
        """Searches files using Google Drive query strings (q parameter)."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files"
        params = {"q": query, "fields": "files(id, name, mimeType, parents)"}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers, params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Drive search_files failed ({res.status_code}): {res.text}")
            return res.json().get("files", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to search Drive files: {e}") from e

    async def read_file(self, file_id: str) -> str:
        """Reads textual content of a document by file_id (alt=media)."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files/{file_id}"
        params = {"alt": "media"}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers, params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Drive read_file failed ({res.status_code}): {res.text}")
            return res.text
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to read Drive file content: {e}") from e

    async def download_file(self, file_id: str) -> Dict[str, Any]:
        """Downloads file contents and returns basic raw contents response metadata."""
        content = await self.read_file(file_id)
        return {"file_id": file_id, "size_chars": len(content), "content_preview": content[:1000]}

    async def upload_file(
        self, name: str, content: str, mime_type: str = "text/plain", parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads a new file using multipart/related encoding."""
        access_token = await self.auth.get_valid_token()
        url = f"{self.upload_url}/files?uploadType=multipart"
        
        boundary = "foo_bar_baz_mcp_boundary"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        }
        
        metadata = {"name": name}
        if parent_id:
            metadata["parents"] = [parent_id]
            
        # Construct multipart body payload
        body_parts = [
            f"--{boundary}\r\n",
            "Content-Type: application/json; charset=UTF-8\r\n\r\n",
            json.dumps(metadata) + "\r\n",
            f"--{boundary}\r\n",
            f"Content-Type: {mime_type}\r\n\r\n",
            content + "\r\n",
            f"--{boundary}--\r\n",
        ]
        body = "".join(body_parts)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, headers=headers, content=body.encode("utf-8"))
            if res.status_code != 200:
                raise ConnectorError(f"Drive upload_file failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to upload file to Drive: {e}") from e

    async def create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a folder in Google Drive."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files"
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=metadata)
            if res.status_code != 200:
                raise ConnectorError(f"Drive create_folder failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to create Drive folder: {e}") from e

    async def move_file(self, file_id: str, add_parents: str, remove_parents: str) -> Dict[str, Any]:
        """Moves a file by updating parents (addParents/removeParents)."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files/{file_id}"
        params = {"addParents": add_parents, "removeParents": remove_parents}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.patch(url, headers=headers, params=params, json={})
            if res.status_code != 200:
                raise ConnectorError(f"Drive move_file failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to move Drive file: {e}") from e

    async def delete_file(self, file_id: str, trash: bool = True) -> Dict[str, Any]:
        """Trashes a file or deletes it permanently."""
        headers = await self._get_headers()
        
        try:
            if trash:
                url = f"{self.base_url}/files/{file_id}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.patch(url, headers=headers, json={"trashed": True})
                if res.status_code != 200:
                    raise ConnectorError(f"Drive trash file failed ({res.status_code}): {res.text}")
                return {"status": "success", "message": "File trashed."}
            else:
                url = f"{self.base_url}/files/{file_id}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.delete(url, headers=headers)
                if res.status_code not in (200, 204):
                    raise ConnectorError(f"Drive delete file failed ({res.status_code}): {res.text}")
                return {"status": "success", "message": "File deleted permanently."}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to delete/trash file: {e}") from e

    async def share_file(self, file_id: str, email_address: str, role: str, type_val: str) -> Dict[str, Any]:
        """Shares a file with a user, group, or domain by creating permissions."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files/{file_id}/permissions"
        payload = {
            "role": role,
            "type": type_val,
            "emailAddress": email_address
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                raise ConnectorError(f"Drive share_file failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to share Drive file: {e}") from e

    async def get_permissions(self, file_id: str) -> List[Dict[str, Any]]:
        """Lists permissions for a Google Drive file."""
        headers = await self._get_headers()
        url = f"{self.base_url}/files/{file_id}/permissions"
        params = {"fields": "permissions(id, role, type, emailAddress)"}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers, params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Drive get_permissions failed ({res.status_code}): {res.text}")
            return res.json().get("permissions", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to list file permissions: {e}") from e
