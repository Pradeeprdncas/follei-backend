"""Unit tests for Slack Connector and Slack SDK operations."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from mcp.base.context import MCPContext
from mcp.base.exceptions import ConnectorError
from mcp.slack.auth import SlackAuth
from mcp.slack.service import SlackService
from mcp.slack.connector import SlackConnector


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
async def test_slack_connector_flow(mock_context) -> None:
    # Mock Slack SDK imports and verify methods
    with patch("mcp.slack.service.SLACK_SDK_AVAILABLE", True), \
         patch("mcp.slack.service.AsyncWebClient") as mock_client_cls:
         
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        service = SlackService(token="mock-slack-token")
        connector = SlackConnector(service)
        
        assert connector.name == "slack"
        assert len(connector.get_tools()) == 9

        # 1. Health check auth test ok
        mock_client.auth_test = AsyncMock(return_value={"ok": True})
        assert await connector.health_check() is True
        
        # 2. Health check auth test fail
        mock_client.auth_test = AsyncMock(return_value={"ok": False})
        assert await connector.health_check() is False
        
        # Test tools execution
        # A. send_message
        mock_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "123.45"})
        res = await connector.execute("slack_send_message", mock_context, {
            "channel": "C12345", "text": "Hello Slack"
        })
        assert res.success is True
        assert res.data["ts"] == "123.45"
        
        # B. list_channels
        mock_client.conversations_list = AsyncMock(return_value={"ok": True, "channels": [{"id": "C1", "name": "general"}]})
        res = await connector.execute("slack_list_channels", mock_context, {"types": "public_channel"})
        assert res.success is True
        assert len(res.data) == 1
        
        # C. get_channel_messages
        mock_client.conversations_history = AsyncMock(return_value={"ok": True, "messages": [{"text": "hi"}]})
        res = await connector.execute("slack_get_channel_messages", mock_context, {"channel": "C1"})
        assert res.success is True
        assert len(res.data) == 1
        
        # D. create_channel
        mock_client.conversations_create = AsyncMock(return_value={"ok": True, "channel": {"id": "C2"}})
        res = await connector.execute("slack_create_channel", mock_context, {"name": "alerts"})
        assert res.success is True
        assert res.data["channel"]["id"] == "C2"
        
        # E. invite_user
        mock_client.conversations_invite = AsyncMock(return_value={"ok": True})
        res = await connector.execute("slack_invite_user", mock_context, {"channel": "C1", "user_id": "U1"})
        assert res.success is True
        
        # F. get_user_info
        mock_client.users_info = AsyncMock(return_value={"ok": True, "user": {"id": "U1", "name": "alice"}})
        res = await connector.execute("slack_get_user_info", mock_context, {"user_id": "U1"})
        assert res.success is True
        assert res.data["name"] == "alice"
        
        # G. search_messages
        mock_client.search_messages = AsyncMock(return_value={"ok": True, "messages": {"matches": [{"text": "found"}]}})
        res = await connector.execute("slack_search_messages", mock_context, {"query": "error"})
        assert res.success is True
        assert len(res.data) == 1
        
        # H. upload_file
        mock_client.files_upload_v2 = AsyncMock(return_value={"ok": True})
        res = await connector.execute("slack_upload_file", mock_context, {
            "channels": "C1", "content": "file-content", "filename": "log.txt"
        })
        assert res.success is True
        
        # I. schedule_message
        mock_client.chat_scheduleMessage = AsyncMock(return_value={"ok": True})
        res = await connector.execute("slack_schedule_message", mock_context, {
            "channel": "C1", "text": "scheduled", "post_at": 1729384850
        })
        assert res.success is True


@pytest.mark.asyncio
async def test_slack_missing_sdk_failure() -> None:
    # Test fallback error checks when SDK is missing
    with patch("mcp.slack.service.SLACK_SDK_AVAILABLE", False):
        service = SlackService(token="mock-token")
        with pytest.raises(ConnectorError):
            await service.send_message("C1", "hi")
