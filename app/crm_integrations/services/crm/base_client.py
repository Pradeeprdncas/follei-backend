from abc import ABC
from typing import Any
from app.crm_integrations.utils.http_client import HTTPClient


class BaseCRMClient(ABC):
    provider: str
    display_name: str
    api_base_url: str

    def __init__(self, access_token: str | None = None, api_key: str | None = None):
        self.access_token = access_token
        self.api_key = api_key
        self.http = HTTPClient(base_url=self.api_base_url, access_token=access_token, api_key=api_key)

    async def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError(f"Real connection test is not implemented for {self.display_name}.")

    async def fetch_contacts(self) -> list[dict[str, Any]]:
        raise NotImplementedError(f"Real contacts endpoint is not implemented for {self.display_name}.")

    async def fetch_leads(self) -> list[dict[str, Any]]:
        raise NotImplementedError(f"Real leads endpoint is not implemented for {self.display_name}.")

    async def push_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"Real lead write endpoint is not implemented for {self.display_name}.")
