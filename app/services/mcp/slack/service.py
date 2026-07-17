"""Slack REST service wrapper using the official Slack SDK."""
from typing import Any, Dict, List, Optional
from loguru import logger
from mcp.base.exceptions import ConnectorError, ExecutionError

# Try to import AsyncWebClient safely
try:
    from slack_sdk.web.async_client import AsyncWebClient
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    AsyncWebClient = None


class SlackService:
    """Orchestrates conversations, users, and files API operations on Slack."""

    def __init__(self, token: str) -> None:
        self.token = token
        if SLACK_SDK_AVAILABLE and AsyncWebClient:
            self.client = AsyncWebClient(token=token)
        else:
            self.client = None
            logger.warning("slack-sdk is not installed. Slack operations will run in fallback mock mode.")

    def _check_sdk(self) -> None:
        if not SLACK_SDK_AVAILABLE or self.client is None:
            raise ConnectorError("Slack SDK is not installed or initialized. Please add slack-sdk to dependencies.")

    async def send_message(self, channel: str, text: str) -> Dict[str, Any]:
        """Posts a message to a public/private channel or direct message."""
        self._check_sdk()
        try:
            res = await self.client.chat_postMessage(channel=channel, text=text)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to post Slack message: {e}") from e

    async def list_channels(self, types: str = "public_channel") -> List[Dict[str, Any]]:
        """Lists channels of specified type in the Slack workspace."""
        self._check_sdk()
        try:
            res = await self.client.conversations_list(types=types)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return list(res.get("channels", []))
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to list Slack channels: {e}") from e

    async def get_channel_messages(self, channel: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves history logs of messages in a channel."""
        self._check_sdk()
        try:
            res = await self.client.conversations_history(channel=channel, limit=limit)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return list(res.get("messages", []))
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to retrieve Slack history: {e}") from e

    async def create_channel(self, name: str, is_private: bool = False) -> Dict[str, Any]:
        """Creates a new channel."""
        self._check_sdk()
        try:
            res = await self.client.conversations_create(name=name, is_private=is_private)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to create Slack channel: {e}") from e

    async def invite_user(self, channel: str, user_id: str) -> Dict[str, Any]:
        """Invites a user to a channel."""
        self._check_sdk()
        try:
            res = await self.client.conversations_invite(channel=channel, users=[user_id])
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to invite user: {e}") from e

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Retrieves profile and detailed information of a user."""
        self._check_sdk()
        try:
            res = await self.client.users_info(user=user_id)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res.get("user", {}))
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to get user info: {e}") from e

    async def search_messages(self, query: str) -> List[Dict[str, Any]]:
        """Searches for messages matching a text query."""
        self._check_sdk()
        try:
            res = await self.client.search_messages(query=query)
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return list(res.get("messages", {}).get("matches", []))
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to search Slack: {e}") from e

    async def upload_file(self, channels: str, content: str, filename: str) -> Dict[str, Any]:
        """Uploads snippet/document content directly to Slack channels."""
        self._check_sdk()
        try:
            # files_upload_v2 is recommended over files_upload which is deprecated
            res = await self.client.files_upload_v2(
                channel=channels,
                content=content,
                filename=filename,
            )
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to upload file to Slack: {e}") from e

    async def schedule_message(self, channel: str, text: str, post_at: float) -> Dict[str, Any]:
        """Schedules a chat message to post at a specific future unix timestamp."""
        self._check_sdk()
        try:
            res = await self.client.chat_scheduleMessage(
                channel=channel,
                text=text,
                post_at=str(int(post_at)),
            )
            if not res.get("ok"):
                raise ConnectorError(f"Slack API error: {res.get('error')}")
            return dict(res)
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to schedule message: {e}") from e
