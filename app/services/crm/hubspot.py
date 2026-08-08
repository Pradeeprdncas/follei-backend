"""HubSpot v3 adapter adapted from Server_crm-main for Follei tenancy."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


HUBSPOT_RESOURCE_COVERAGE = {
    "contacts": {"status": "implemented", "object_type": "contact"},
    "companies": {"status": "implemented", "object_type": "company"},
    "deals": {"status": "implemented", "object_type": "deal"},
    "owners": {"status": "pending", "object_type": None},
    "pipelines": {"status": "pending", "object_type": None},
    "associations": {"status": "pending", "object_type": None},
    "property_schemas": {"status": "pending", "object_type": None},
    "engagements": {"status": "pending", "object_type": None},
}


class HubSpotError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class HubSpotPage:
    records: list[dict[str, Any]]
    after: str | None


class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"
    PATHS = {
        "contact": "/crm/v3/objects/contacts",
        "company": "/crm/v3/objects/companies",
        "deal": "/crm/v3/objects/deals",
    }
    PROPERTIES = {
        "contact": ("firstname", "lastname", "email", "phone", "company", "lifecyclestage", "hs_lead_status", "lastmodifieddate"),
        "company": ("name", "domain", "website", "industry", "phone", "lifecyclestage", "hs_lastmodifieddate"),
        "deal": ("dealname", "amount", "dealstage", "pipeline", "closedate", "hubspot_owner_id", "hs_lastmodifieddate"),
    }

    def __init__(self, access_token: str, *, client: httpx.AsyncClient | None = None, timeout: float = 30.0):
        if not access_token.strip():
            raise ValueError("HubSpot access token is required")
        self.access_token = access_token.strip()
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None, attempts: int = 3) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json", "Content-Type": "application/json"}
        for attempt in range(attempts):
            try:
                response = await self._http().request(method, url, params=params, json=json, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 == attempts:
                    raise HubSpotError(f"HubSpot network failure after {attempts} attempts") from exc
                await asyncio.sleep(0.25 * (2 ** attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < attempts:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(float(retry_after), 5.0) if retry_after else 0.25 * (2 ** attempt)
                    except ValueError:
                        delay = 0.25 * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
            if response.status_code >= 400:
                request_id = response.headers.get("x-hubspot-correlation-id") or response.headers.get("x-request-id")
                raise HubSpotError(f"HubSpot returned {response.status_code}; request_id={request_id or 'unknown'}", status_code=response.status_code)
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise HubSpotError("HubSpot returned a non-JSON response", status_code=response.status_code) from exc
        raise HubSpotError("HubSpot request exhausted retries")

    async def list_page(self, object_type: str, *, limit: int = 100, after: str | None = None) -> HubSpotPage:
        if object_type not in self.PATHS:
            raise ValueError(f"Unsupported HubSpot object type: {object_type}")
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 100)), "properties": ",".join(self.PROPERTIES[object_type]), "archived": "false"}
        if after:
            params["after"] = after
        payload = await self._request("GET", self.PATHS[object_type], params=params)
        next_after = (((payload.get("paging") or {}).get("next") or {}).get("after"))
        return HubSpotPage(records=list(payload.get("results") or []), after=str(next_after) if next_after is not None else None)

    async def validate(self) -> None:
        await self.list_page("contact", limit=1)


def normalize_hubspot_record(object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    properties = dict(payload.get("properties") or {})
    external_id = str(payload.get("id") or "").strip()
    if not external_id:
        raise ValueError("HubSpot record has no id")
    base = {"external_id": external_id, "archived": bool(payload.get("archived")), "created_at": payload.get("createdAt"), "updated_at": payload.get("updatedAt")}
    if object_type == "contact":
        return {**base, "first_name": properties.get("firstname"), "last_name": properties.get("lastname"), "email": properties.get("email"), "phone": properties.get("phone"), "company": properties.get("company"), "lifecycle_stage": properties.get("lifecyclestage"), "lead_status": properties.get("hs_lead_status")}
    if object_type == "company":
        return {**base, "name": properties.get("name"), "domain": properties.get("domain"), "website": properties.get("website"), "industry": properties.get("industry"), "phone": properties.get("phone"), "lifecycle_stage": properties.get("lifecyclestage")}
    if object_type == "deal":
        amount = properties.get("amount")
        try:
            amount = float(amount) if amount not in (None, "") else None
        except (TypeError, ValueError):
            amount = None
        return {**base, "title": properties.get("dealname"), "amount": amount, "stage": properties.get("dealstage"), "pipeline": properties.get("pipeline"), "close_date": properties.get("closedate"), "owner_id": properties.get("hubspot_owner_id")}
    raise ValueError(f"Unsupported HubSpot object type: {object_type}")
