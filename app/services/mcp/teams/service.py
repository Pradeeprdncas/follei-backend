"""MS Graph Teams REST API service integration wrapper."""
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from mcp.base.exceptions import ConnectorError, ExecutionError
from mcp.teams.auth import TeamsAuth


class TeamsService:
    """Wrapper for calling Microsoft Graph REST endpoints for MS Teams using HTTPX."""

    def __init__(self, auth: TeamsAuth) -> None:
        self.auth = auth
        self.base_url = "https://graph.microsoft.com/v1.0"

    async def _get_headers(self) -> Dict[str, str]:
        access_token = await self.auth.get_valid_token()
        headers = self.auth.get_auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    async def list_teams(self) -> List[Dict[str, Any]]:
        """Lists joined Teams for the authenticated user context."""
        headers = await self._get_headers()
        url = f"{self.base_url}/me/joinedTeams"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ConnectorError(f"Teams list_teams failed ({res.status_code}): {res.text}")
            return res.json().get("value", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to list Teams: {e}") from e

    async def list_channels(self, team_id: str) -> List[Dict[str, Any]]:
        """Lists channels within a specific Team."""
        headers = await self._get_headers()
        url = f"{self.base_url}/teams/{team_id}/channels"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ConnectorError(f"Teams list_channels failed ({res.status_code}): {res.text}")
            return res.json().get("value", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to list Teams channels: {e}") from e

    async def send_message(
        self, text: str, chat_id: Optional[str] = None, channel_id: Optional[str] = None, team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends a message to a direct chat or a Team channel."""
        headers = await self._get_headers()
        payload = {"body": {"contentType": "text", "content": text}}
        
        try:
            if channel_id and team_id:
                url = f"{self.base_url}/teams/{team_id}/channels/{channel_id}/messages"
            elif chat_id:
                url = f"{self.base_url}/chats/{chat_id}/messages"
            else:
                raise ConnectorError("Must specify either (channel_id and team_id) or chat_id to send a message.")

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Teams send_message failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to send Teams message: {e}") from e

    async def get_messages(
        self, chat_id: Optional[str] = None, channel_id: Optional[str] = None, team_id: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Retrieves history message logs from chat or channel."""
        headers = await self._get_headers()
        params = {"$top": limit}
        
        try:
            if channel_id and team_id:
                url = f"{self.base_url}/teams/{team_id}/channels/{channel_id}/messages"
            elif chat_id:
                url = f"{self.base_url}/chats/{chat_id}/messages"
            else:
                raise ConnectorError("Must specify either (channel_id and team_id) or chat_id to get messages.")

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers, params=params)
            if res.status_code != 200:
                raise ConnectorError(f"Teams get_messages failed ({res.status_code}): {res.text}")
            return res.json().get("value", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to retrieve Teams messages: {e}") from e

    async def create_channel(self, team_id: str, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """Creates a channel in a specific Team."""
        headers = await self._get_headers()
        url = f"{self.base_url}/teams/{team_id}/channels"
        payload = {"displayName": name}
        if description:
            payload["description"] = description

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Teams create_channel failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to create Teams channel: {e}") from e

    async def add_member(self, team_id: str, user_id: str, roles: Optional[List[str]] = None) -> Dict[str, Any]:
        """Adds a member user to a Team."""
        headers = await self._get_headers()
        url = f"{self.base_url}/teams/{team_id}/members"
        payload = {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": roles or [],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{user_id}",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Teams add_member failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to add Teams member: {e}") from e

    async def schedule_meeting(self, subject: str, start_time: str, end_time: str) -> Dict[str, Any]:
        """Schedules a virtual online Teams meeting."""
        headers = await self._get_headers()
        url = f"{self.base_url}/me/onlineMeetings"
        payload = {
            "startDateTime": start_time,
            "endDateTime": end_time,
            "subject": subject
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                raise ConnectorError(f"Teams schedule_meeting failed ({res.status_code}): {res.text}")
            return res.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to schedule Teams meeting: {e}") from e
