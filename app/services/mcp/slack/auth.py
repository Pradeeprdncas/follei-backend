"""Slack credential authentication handler."""
from typing import Dict, Optional


class SlackAuth:
    """Manages Slack API tokens and authorization headers."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def get_valid_token(self) -> str:
        """Returns the current valid Slack bot or user token."""
        return self.token

    def get_auth_headers(self) -> Dict[str, str]:
        """Returns bearer token authorization headers."""
        return {"Authorization": f"Bearer {self.token}"}
