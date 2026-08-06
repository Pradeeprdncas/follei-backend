import httpx
import pytest
import uuid

from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.services.crm.hubspot import HubSpotClient, HubSpotError, normalize_hubspot_record
from app.services.knowledge.outbox import _deliveries, deliver_event


@pytest.mark.asyncio
async def test_hubspot_list_page_requests_explicit_properties_and_cursor():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"results": [{"id": "101", "properties": {"email": "lead@example.com"}}], "paging": {"next": {"after": "202"}}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = HubSpotClient("secret-token", client=http)
    page = await client.list_page("contact", limit=25, after="100")
    await http.aclose()

    assert page.after == "202"
    assert page.records[0]["id"] == "101"
    assert "properties=firstname" in seen["url"]
    assert "after=100" in seen["url"]
    assert seen["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_hubspot_error_does_not_expose_token_or_provider_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"message":"provider may echo sensitive request data"}', headers={"x-hubspot-correlation-id": "corr-1"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = HubSpotClient("super-secret-token", client=http)
    with pytest.raises(HubSpotError) as caught:
        await client.list_page("contact")
    await http.aclose()

    assert "super-secret-token" not in str(caught.value)
    assert "provider may echo" not in str(caught.value)
    assert "corr-1" in str(caught.value)


def test_normalization_keeps_operational_fields_not_raw_payload():
    normalized = normalize_hubspot_record("contact", {"id": "42", "createdAt": "2026-08-01T00:00:00Z", "properties": {"firstname": "Nina", "lastname": "R", "email": "nina@example.com", "lifecyclestage": "customer", "custom_secret": "raw-only"}})
    assert normalized["external_id"] == "42"
    assert normalized["email"] == "nina@example.com"
    assert normalized["lifecycle_stage"] == "customer"
    assert "custom_secret" not in normalized


def test_crm_sync_event_targets_both_projection_stores():
    assert _deliveries("crm.record.synced") == {"postgres": "completed", "ferret": "pending", "qdrant": "pending"}


@pytest.mark.asyncio
async def test_completed_projection_redacts_raw_crm_payload_from_postgres_event():
    event = KnowledgeSyncEvent(
        tenant_id=uuid.uuid4(), event_type="crm.record.synced", aggregate_type="crm_record", aggregate_id=uuid.uuid4(),
        idempotency_key="crm:test", payload={"raw": {"private_custom_field": "value"}, "normalized": {"email": "a@example.com"}},
        deliveries={"postgres": "completed", "ferret": "pending", "qdrant": "pending"},
    )
    handlers = {"ferret": lambda _: "completed", "qdrant": lambda _: "completed"}
    await deliver_event(event, handlers=handlers)
    assert event.status == "completed"
    assert "raw" not in event.payload
    assert event.payload["raw_projected"] is True
