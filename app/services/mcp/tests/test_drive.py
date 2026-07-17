"""Unit tests for Google Drive Connector and API Rest methods."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from mcp.base.context import MCPContext
from mcp.base.exceptions import ConnectorError
from mcp.drive.auth import DriveAuth
from mcp.drive.service import DriveService
from mcp.drive.connector import DriveConnector


@pytest.fixture
def mock_context() -> MCPContext:
    return MCPContext(
        organization_id="org_test",
        user_id="user_test",
        agent_id="agent_test",
        permissions=["*"],
        request_id="req_test",
        trace_id="trace_test"
    )


@pytest.mark.asyncio
async def test_drive_auth_token_refresh() -> None:
    auth = DriveAuth(
        client_id="cid", client_secret="cs", refresh_token="rt"
    )
    assert auth.is_token_expired() is True
    
    mock_res = httpx.Response(200, json={"access_token": "drive_token", "expires_in": 3600})
    with patch("httpx.AsyncClient.post", return_value=mock_res):
        await auth.refresh()
        assert auth.access_token == "drive_token"
        assert auth.is_token_expired() is False
        assert auth.get_auth_headers() == {"Authorization": "Bearer drive_token"}


@pytest.mark.asyncio
async def test_drive_connector_execution(mock_context) -> None:
    auth = DriveAuth("cid", "cs", "rt")
    auth.get_valid_token = AsyncMock(return_value="drive_token")
    service = DriveService(auth)
    connector = DriveConnector(auth, service)

    assert connector.name == "drive"
    assert len(connector.get_tools()) == 10

    # Mock health checks
    mock_about_ok = httpx.Response(200, json={"user": {"displayName": "Alice"}})
    with patch("httpx.AsyncClient.get", return_value=mock_about_ok):
        assert await connector.health_check() is True

    # 1. list_files
    mock_list = httpx.Response(200, json={"files": [{"id": "f1", "name": "document.txt"}]})
    with patch("httpx.AsyncClient.get", return_value=mock_list):
        res = await connector.execute("drive_list_files", mock_context, {"page_size": 10})
        assert res.success is True
        assert len(res.data) == 1
        assert res.data[0]["name"] == "document.txt"

    # 2. search_files
    with patch("httpx.AsyncClient.get", return_value=mock_list):
        res = await connector.execute("drive_search_files", mock_context, {"query": "name contains 'document'"})
        assert res.success is True
        assert len(res.data) == 1

    # 3. read_file
    mock_media = httpx.Response(200, text="File content text")
    with patch("httpx.AsyncClient.get", return_value=mock_media):
        res = await connector.execute("drive_read_file", mock_context, {"file_id": "f1"})
        assert res.success is True
        assert res.data == "File content text"

    # 4. download_file
    with patch("httpx.AsyncClient.get", return_value=mock_media):
        res = await connector.execute("drive_download_file", mock_context, {"file_id": "f1"})
        assert res.success is True
        assert res.data["file_id"] == "f1"
        assert "content_preview" in res.data

    # 5. upload_file
    mock_upload = httpx.Response(200, json={"id": "f2", "name": "newfile.txt"})
    with patch("httpx.AsyncClient.post", return_value=mock_upload):
        res = await connector.execute("drive_upload_file", mock_context, {
            "name": "newfile.txt", "content": "uploaded data"
        })
        assert res.success is True
        assert res.data["id"] == "f2"

    # 6. create_folder
    mock_folder = httpx.Response(200, json={"id": "f_folder", "mimeType": "application/vnd.google-apps.folder"})
    with patch("httpx.AsyncClient.post", return_value=mock_folder):
        res = await connector.execute("drive_create_folder", mock_context, {"name": "My Folder"})
        assert res.success is True
        assert res.data["id"] == "f_folder"

    # 7. move_file
    mock_move = httpx.Response(200, json={"id": "f1", "parents": ["folder_id"]})
    with patch("httpx.AsyncClient.patch", return_value=mock_move):
        res = await connector.execute("drive_move_file", mock_context, {
            "file_id": "f1", "add_parents": "folder_id", "remove_parents": "old_id"
        })
        assert res.success is True

    # 8. delete_file (trash)
    mock_trash = httpx.Response(200, json={"trashed": True})
    with patch("httpx.AsyncClient.patch", return_value=mock_trash):
        res = await connector.execute("drive_delete_file", mock_context, {"file_id": "f1", "trash": True})
        assert res.success is True
        assert "trashed" in res.data["message"]

    # 9. share_file
    mock_share = httpx.Response(200, json={"id": "perm_id", "role": "reader"})
    with patch("httpx.AsyncClient.post", return_value=mock_share):
        res = await connector.execute("drive_share_file", mock_context, {
            "file_id": "f1", "email_address": "user@gmail.com", "role": "reader", "type": "user"
        })
        assert res.success is True

    # 10. get_permissions
    mock_perms = httpx.Response(200, json={"permissions": [{"id": "p1", "role": "owner"}]})
    with patch("httpx.AsyncClient.get", return_value=mock_perms):
        res = await connector.execute("drive_get_permissions", mock_context, {"file_id": "f1"})
        assert res.success is True
        assert len(res.data) == 1
