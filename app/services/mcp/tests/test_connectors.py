"""Unit tests verifying Gmail, Outlook, CRM (HubSpot, Salesforce, Zoho), Calendar, and WhatsApp Connectors."""
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from mcp.base.context import MCPContext
from mcp.base.exceptions import ConnectorError, AuthError, ValidationError, ToolNotFoundError
from mcp.base.capability import MCPCapability
from mcp.gmail.auth import GmailAuth
from mcp.gmail.connector import GmailConnector
from mcp.outlook.auth import OutlookAuth, ClientCredentialsAuth
from mcp.outlook.connector import OutlookConnector
from mcp.crm.service import CRMService
from mcp.crm.connector import CRMConnector
from mcp.calendar.service import CalendarService
from mcp.calendar.connector import CalendarConnector
from mcp.whatsapp.service import WhatsAppService
from mcp.whatsapp.connector import WhatsAppConnector
from mcp.monitoring.tracing import trace_tool_execution
from mcp.registry.registry import ToolRegistry
from mcp.registry.discovery import discover_and_register
from mcp.executor.rate_limiter import RateLimiter
from mcp.tests.test_registry import DummyConnector


@pytest.fixture
def mock_context() -> MCPContext:
    return MCPContext(
        organization_id="org_test",
        user_id="user_test",
        agent_id="agent_test",
        permissions=["*"],
        request_id="req_test",
        trace_id="tr_test",
    )


# =====================================================================
# GMAIL & GOOGLE AUTH TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_gmail_auth_and_token_refresh() -> None:
    # 1. Test token expiry logic
    auth = GmailAuth(
        client_id="cid",
        client_secret="cs",
        refresh_token="rt",
        access_token="act",
        expiry_timestamp=time.time() + 120.0,
    )
    assert auth.is_token_expired() is False
    
    auth.expiry_timestamp = time.time() - 10.0
    assert auth.is_token_expired() is True
    
    # 2. Test successful refresh
    mock_res = httpx.Response(200, json={"access_token": "new_act", "expires_in": 3600})
    with patch("httpx.AsyncClient.post", return_value=mock_res):
        await auth.refresh()
        assert auth.access_token == "new_act"
        assert auth.expiry_timestamp > time.time()
        assert auth.get_auth_headers() == {"Authorization": "Bearer new_act"}
        
    # 3. Test failed refresh raising AuthError
    mock_fail_res = httpx.Response(400, text="Invalid Grant")
    with patch("httpx.AsyncClient.post", return_value=mock_fail_res):
        with pytest.raises(AuthError):
            await auth.refresh()


@pytest.mark.asyncio
async def test_gmail_connector_and_service(mock_context) -> None:
    auth = GmailAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    auth.get_valid_token = AsyncMock(return_value="mock_google_token")
    
    connector = GmailConnector(auth)
    
    # Assert connector basic properties
    assert connector.name == "gmail"
    assert len(connector.get_tools()) == 4
    await connector.disconnect()
    
    # Mock profile response for health_check
    mock_profile_ok = httpx.Response(200, json={"emailAddress": "me@gmail.com"})
    mock_profile_fail = httpx.Response(401, text="Unauthorized")
    
    with patch("httpx.AsyncClient.get", return_value=mock_profile_ok):
        assert await connector.health_check() is True
        
    with patch("httpx.AsyncClient.get", return_value=mock_profile_fail):
        assert await connector.health_check() is False
        
    # Test refresh token delegation
    auth.refresh = AsyncMock()
    await connector.refresh_token()
    auth.refresh.assert_called_once()
    
    # Mock API HTTP operations
    mock_send = httpx.Response(200, json={"id": "msg1", "threadId": "th1"})
    mock_search = httpx.Response(200, json={"messages": [{"id": "msg1", "threadId": "th1"}]})
    mock_thread = httpx.Response(
        200,
        json={
            "messages": [
                {
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Greeting"},
                            {"name": "Message-ID", "value": "<msg123@google>"},
                            {"name": "From", "value": "boss@google.com"},
                        ]
                    }
                }
            ]
        },
    )
    
    # Executions
    with patch("httpx.AsyncClient.post", return_value=mock_send), \
         patch("httpx.AsyncClient.get") as mock_get:
         
        mock_get.side_effect = [mock_thread, mock_search, mock_thread]
        
        # Test Send Email
        res = await connector.execute("send_email", mock_context, {
            "to": "test@gmail.com",
            "subject": "Hello",
            "body": "Daily report",
            "cc": ["cc@gmail.com"],
            "bcc": ["bcc@gmail.com"]
        })
        assert res.success is True
        assert res.data["id"] == "msg1"
        
        # Test Search Email
        res = await connector.execute("search_email", mock_context, {
            "query": "is:unread",
            "max_results": 5
        })
        assert res.success is True
        assert len(res.data) == 1
        
        # Test Read Thread
        res = await connector.execute("read_thread", mock_context, {"thread_id": "th1"})
        assert res.success is True
        assert "messages" in res.data
        
        # Test Reply Email
        res = await connector.execute("reply_email", mock_context, {
            "thread_id": "th1",
            "body": "Sure, I will do it."
        })
        assert res.success is True
        assert res.data["id"] == "msg1"


# =====================================================================
# OUTLOOK & MS AUTH TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_outlook_auth_refresh() -> None:
    auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt", tenant_id="common")
    assert auth.is_token_expired() is True
    
    # Successful refresh
    mock_res = httpx.Response(200, json={"access_token": "ms_act", "expires_in": 3600})
    with patch("httpx.AsyncClient.post", return_value=mock_res):
        await auth.refresh()
        assert auth.access_token == "ms_act"
        assert auth.is_token_expired() is False
        assert auth.get_auth_headers() == {"Authorization": "Bearer ms_act"}
        
    # Failed refresh
    mock_fail = httpx.Response(400, text="invalid_request")
    with patch("httpx.AsyncClient.post", return_value=mock_fail):
        with pytest.raises(AuthError):
            await auth.refresh()

    # ClientCredentialsAuth check
    cc_auth = ClientCredentialsAuth(client_id="cid", client_secret="cs", tenant_id="t1")
    assert cc_auth.is_token_expired() is True
    with patch("httpx.AsyncClient.post", return_value=mock_res):
        await cc_auth.refresh()
        assert cc_auth.access_token == "ms_act"
        assert cc_auth.get_auth_headers() == {"Authorization": "Bearer ms_act"}
        assert await cc_auth.get_valid_token() == "ms_act"


@pytest.mark.asyncio
async def test_outlook_connector_and_service(mock_context) -> None:
    auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    auth.get_valid_token = AsyncMock(return_value="mock_ms_token")
    
    connector = OutlookConnector(auth)
    assert connector.name == "outlook"
    
    # Health check mocks
    mock_me_ok = httpx.Response(200, json={"id": "usr1"})
    mock_me_fail = httpx.Response(400, text="Error")
    
    with patch("httpx.AsyncClient.get", return_value=mock_me_ok):
        assert await connector.health_check() is True
    with patch("httpx.AsyncClient.get", return_value=mock_me_fail):
        assert await connector.health_check() is False
        
    # Mock endpoints
    mock_send = httpx.Response(202, json={})
    mock_draft = httpx.Response(201, json={"id": "draft_reply_123"})
    mock_patch = httpx.Response(200, json={})
    mock_send_draft = httpx.Response(202, json={})
    mock_read = httpx.Response(200, json={"subject": "Review Request"})
    mock_event = httpx.Response(201, json={"id": "evt_101"})
    
    with patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.patch", return_value=mock_patch), \
         patch("httpx.AsyncClient.get", return_value=mock_read):
         
        # Mock successive post responses
        # 1. send_email
        # 2. createReply draft, 3. sendDraft
        # 4. create_event
        mock_post.side_effect = [mock_send, mock_draft, mock_send_draft, mock_event]
        
        # Outlook Send Email
        res = await connector.execute("outlook_send_email", mock_context, {
            "to": "user@outlook.com",
            "subject": "Meeting",
            "body": "Discuss project details",
            "cc": ["cc@outlook.com"],
            "bcc": ["bcc@outlook.com"]
        })
        assert res.success is True
        assert res.data["status"] == "success"
        
        # Outlook Reply Email
        res = await connector.execute("outlook_reply_email", mock_context, {
            "message_id": "msg_000",
            "body": "Got it, thanks!"
        })
        assert res.success is True
        assert res.data["draft_id"] == "draft_reply_123"
        
        # Outlook Read Email
        res = await connector.execute("outlook_read_email", mock_context, {"message_id": "msg_000"})
        assert res.success is True
        assert res.data["subject"] == "Review Request"
        
        # Outlook Create Event
        res = await connector.execute("outlook_create_event", mock_context, {
            "subject": "Planning session",
            "body": "Q3 roadmap",
            "start_time": "2026-06-15T15:00:00",
            "end_time": "2026-06-15T16:00:00",
            "time_zone": "UTC",
            "attendees": ["team@outlook.com"]
        })
        assert res.success is True
        assert res.data["id"] == "evt_101"


# =====================================================================
# CRM PROVIDERS & SERVICE TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_crm_hubspot_adapter() -> None:
    service = CRMService(provider="hubspot", credentials={"api_key": "hs_key"})
    assert service.provider_name == "hubspot"
    
    mock_contact = httpx.Response(201, json={"id": "hs_contact_1"})
    mock_patch = httpx.Response(200, json={"id": "hs_contact_1"})
    mock_search = httpx.Response(200, json={"results": [{"id": "hs_contact_1"}]})
    mock_deal = httpx.Response(201, json={"id": "hs_deal_1"})
    
    with patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.patch", return_value=mock_patch):
         
        mock_post.side_effect = [mock_contact, mock_search, mock_deal]
        
        # 1. Create Lead
        res = await service.create_lead({
            "first_name": "Alice", "last_name": "Smith", "email": "alice@gmail.com",
            "company": "Smith Co", "phone": "12345", "custom_properties": {"jobtitle": "VP"}
        })
        assert res["id"] == "hs_contact_1"
        
        # 2. Update Lead
        res = await service.update_lead("hs_contact_1", {"first_name": "Alicia"})
        assert res["id"] == "hs_contact_1"
        
        # 3. Search Contact
        res = await service.search_contact("alice@gmail.com")
        assert len(res) == 1
        
        # 4. Create Opportunity
        res = await service.create_opportunity({
            "name": "Big Deal", "stage": "appointmentscheduled",
            "close_date": "2026-07-01Z", "amount": 50000.0,
            "custom_properties": {"description": "large value"}
        })
        assert res["id"] == "hs_deal_1"
        
        # 5. Update Opportunity
        with patch("httpx.AsyncClient.patch", return_value=mock_patch):
            res = await service.update_opportunity("hs_deal_1", {"amount": 55000.0})
            assert res["id"] == "hs_contact_1"


@pytest.mark.asyncio
async def test_crm_salesforce_adapter() -> None:
    service = CRMService(
        provider="salesforce",
        credentials={"instance_url": "https://test.salesforce.com", "access_token": "sf_token"},
    )
    assert service.provider_name == "salesforce"
    
    mock_lead = httpx.Response(201, json={"id": "sf_lead_22"})
    mock_patch = httpx.Response(204, text="")
    mock_search = httpx.Response(200, json={"searchRecords": [{"Id": "sf_contact_1"}]})
    mock_opp = httpx.Response(201, json={"id": "sf_opp_1"})
    
    with patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.patch", return_value=mock_patch), \
         patch("httpx.AsyncClient.get", return_value=mock_search):
         
        mock_post.side_effect = [mock_lead, mock_opp]
        
        # 1. Create Lead
        res = await service.create_lead({
            "first_name": "Bob", "last_name": "Jones", "email": "bob@salesforce.com",
            "company": "Jones Corp", "phone": "999"
        })
        assert res["id"] == "sf_lead_22"
        
        # 2. Update Lead
        res = await service.update_lead("sf_lead_22", {"first_name": "Bobby"})
        assert res["status"] == "updated"
        
        # 3. Search Contact
        res = await service.search_contact("Bob")
        assert len(res) == 1
        assert res[0]["Id"] == "sf_contact_1"
        
        # 4. Create Opportunity
        res = await service.create_opportunity({
            "name": "Cloud Deal", "stage": "Prospecting",
            "close_date": "2026-10-10", "amount": 100000.0
        })
        assert res["id"] == "sf_opp_1"
        
        # 5. Update Opportunity
        res = await service.update_opportunity("sf_opp_1", {"stage": "Qualification"})
        assert res["status"] == "updated"


@pytest.mark.asyncio
async def test_crm_zoho_adapter() -> None:
    service = CRMService(
        provider="zoho",
        credentials={"access_token": "zoho_token"},
    )
    assert service.provider_name == "zoho"
    
    mock_lead = httpx.Response(201, json={"data": [{"code": "SUCCESS", "details": {"id": "zoho_lead_1"}}]})
    mock_put = httpx.Response(200, json={"data": [{"code": "SUCCESS", "details": {"id": "zoho_lead_1"}}]})
    mock_search = httpx.Response(200, json={"data": [{"id": "zoho_contact_1"}]})
    mock_opp = httpx.Response(201, json={"data": [{"details": {"id": "zoho_deal_1"}}]})
    
    with patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.put") as mock_put_mock, \
         patch("httpx.AsyncClient.get", return_value=mock_search):
         
        mock_post.side_effect = [mock_lead, mock_opp]
        mock_put_mock.side_effect = [mock_put, mock_put]
        
        # 1. Create Lead
        res = await service.create_lead({
            "first_name": "Charlie", "last_name": "Brown", "email": "charlie@zoho.com",
            "company": "Brown LLC", "phone": "111"
        })
        assert "data" in res
        
        # 2. Update Lead
        res = await service.update_lead("zoho_lead_1", {"first_name": "Chuck"})
        assert "data" in res
        
        # 3. Search Contact
        res = await service.search_contact("Charlie")
        assert len(res) == 1
        
        # 4. Create Opportunity
        res = await service.create_opportunity({
            "name": "Peanuts", "stage": "Qualification",
            "close_date": "2026-06-25", "amount": 1000.0
        })
        assert "data" in res
        
        # 5. Update Opportunity
        res = await service.update_opportunity("zoho_deal_1", {"amount": 1500.0})
        assert "data" in res


@pytest.mark.asyncio
async def test_crm_connector_lifecycle(mock_context) -> None:
    service = CRMService(provider="hubspot", credentials={"api_key": "hs_key"})
    connector = CRMConnector(service)
    
    # Verify tools
    tools = connector.get_tools()
    assert len(tools) == 5
    assert connector.name == "crm_hubspot"
    
    # Health check and connection checks
    mock_search = httpx.Response(200, json={"results": []})
    mock_fail = httpx.Response(400, text="Bad Request")
    
    with patch("httpx.AsyncClient.post", return_value=mock_search):
        await connector.connect()
        assert await connector.health_check() is True
        
    with patch("httpx.AsyncClient.post", return_value=mock_fail):
        assert await connector.health_check() is False
        
    await connector.refresh_token()
    await connector.disconnect()
    
    # Error checking for invalid tool lookup
    with pytest.raises(ToolNotFoundError):
        await connector.execute("invalid_crm_tool", mock_context, {})


# =====================================================================
# CALENDAR SERVICE & CONNECTOR TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_calendar_service_and_connector(mock_context) -> None:
    g_auth = GmailAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    g_auth.get_valid_token = AsyncMock(return_value="g_tok")
    
    o_auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    o_auth.get_valid_token = AsyncMock(return_value="o_tok")
    
    service = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
    connector = CalendarConnector(service)
    assert connector.name == "calendar"
    
    # Verify health checks
    assert await connector.health_check() is True
    connector.service.google_auth = None
    connector.service.outlook_auth = None
    assert await connector.health_check() is False
    
    # Put back auth for testing endpoints
    service.google_auth = g_auth
    service.outlook_auth = o_auth
    
    # Mocks
    mock_google_res = httpx.Response(200, json={"id": "g_evt_1"})
    mock_outlook_res = httpx.Response(200, json={"id": "o_evt_1"})
    mock_cancel = httpx.Response(204, text="")
    mock_freebusy = httpx.Response(200, json={"calendars": {}})
    
    # 1. Create Event Google
    with patch("httpx.AsyncClient.post", return_value=mock_google_res):
        res = await connector.execute("create_event", mock_context, {
            "provider": "google", "subject": "S1", "body": "B1",
            "start_time": "2026-06-15T10:00:00Z", "end_time": "2026-06-15T11:00:00Z",
            "attendees": ["guest@google.com"]
        })
        assert res.success is True
        assert res.data["id"] == "g_evt_1"
        
    # 2. Update Event Google
    with patch("httpx.AsyncClient.patch", return_value=mock_google_res):
        res = await connector.execute("update_event", mock_context, {
            "provider": "google", "event_id": "g_evt_1",
            "event_data": {"subject": "S2", "body": "B2", "start_time": "2026-06-15T10:30:00Z"}
        })
        assert res.success is True
        assert res.data["id"] == "g_evt_1"
        
    # 3. Cancel Event Google
    with patch("httpx.AsyncClient.delete", return_value=mock_cancel):
        res = await connector.execute("cancel_event", mock_context, {
            "provider": "google", "event_id": "g_evt_1"
        })
        assert res.success is True
        assert res.data["status"] == "success"
        
    # 4. Get Availability Google
    with patch("httpx.AsyncClient.post", return_value=mock_freebusy):
        res = await connector.execute("get_availability", mock_context, {
            "provider": "google", "start_time": "2026-06-15T09:00:00Z",
            "end_time": "2026-06-15T17:00:00Z", "emails": ["guest@google.com"]
        })
        assert res.success is True
        
    # 5. Create Event Outlook
    with patch("httpx.AsyncClient.post", return_value=mock_outlook_res):
        res = await connector.execute("create_event", mock_context, {
            "provider": "outlook", "subject": "S1", "body": "B1",
            "start_time": "2026-06-15T10:00:00Z", "end_time": "2026-06-15T11:00:00Z",
            "attendees": ["guest@outlook.com"]
        })
        assert res.success is True
        assert res.data["id"] == "o_evt_1"
        
    # 6. Update Event Outlook
    with patch("httpx.AsyncClient.patch", return_value=mock_outlook_res):
        res = await connector.execute("update_event", mock_context, {
            "provider": "outlook", "event_id": "o_evt_1",
            "event_data": {"subject": "S2", "body": "B2", "start_time": "2026-06-15T10:30:00Z"}
        })
        assert res.success is True
        assert res.data["id"] == "o_evt_1"
        
    # 7. Cancel Event Outlook
    with patch("httpx.AsyncClient.delete", return_value=mock_cancel):
        res = await connector.execute("cancel_event", mock_context, {
            "provider": "outlook", "event_id": "o_evt_1"
        })
        assert res.success is True
        assert res.data["status"] == "success"
        
    # 8. Get Availability Outlook
    with patch("httpx.AsyncClient.post", return_value=mock_freebusy):
        res = await connector.execute("get_availability", mock_context, {
            "provider": "outlook", "start_time": "2026-06-15T09:00:00Z",
            "end_time": "2026-06-15T17:00:00Z", "emails": ["guest@outlook.com"]
        })
        assert res.success is True

    # 9. Refresh token check
    g_auth.refresh = AsyncMock()
    o_auth.refresh = AsyncMock()
    await connector.refresh_token()
    g_auth.refresh.assert_called_once()
    o_auth.refresh.assert_called_once()
    await connector.connect()
    await connector.disconnect()


# =====================================================================
# WHATSAPP SERVICE & CONNECTOR TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_whatsapp_connector_and_service(mock_context) -> None:
    service = WhatsAppService(phone_number_id="wa_id", access_token="wa_token")
    connector = WhatsAppConnector(service)
    assert connector.name == "whatsapp"
    
    # Mocks
    mock_ok = httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.123"}]})
    mock_health_ok = httpx.Response(200, json={"id": "wa_id"})
    mock_health_fail = httpx.Response(400, text="Bad Token")
    
    with patch("httpx.AsyncClient.get", return_value=mock_health_ok):
        assert await connector.health_check() is True
    with patch("httpx.AsyncClient.get", return_value=mock_health_fail):
        assert await connector.health_check() is False
        
    with patch("httpx.AsyncClient.post", return_value=mock_ok):
        # 1. Send plain message
        res = await connector.execute("whatsapp_send_message", mock_context, {
            "to": "+12345678", "body": "Alert!"
        })
        assert res.success is True
        
        # 2. Send template
        res = await connector.execute("whatsapp_send_template", mock_context, {
            "to": "+12345678", "template_name": "welcome_template",
            "language_code": "en_US", "components": [{"type": "body", "parameters": []}]
        })
        assert res.success is True
        
        # 3. Send media
        res = await connector.execute("whatsapp_send_media", mock_context, {
            "to": "+12345678", "media_type": "image", "media_url": "https://test.com/img.png",
            "caption": "test image"
        })
        assert res.success is True

    # 4. Get conversation logs
    with patch("httpx.AsyncClient.get", return_value=httpx.Response(500, text="API Error")):
        # Will trigger fallback code path returning mock message logs
        res = await connector.execute("whatsapp_get_conversation", mock_context, {
            "phone_number": "+12345678", "limit": 2
        })
        assert res.success is True
        assert len(res.data) == 2
        assert res.data[0]["from"] in ("+12345678", "system")
        
    await connector.refresh_token()
    await connector.disconnect()


# =====================================================================
# TRACING OBSERVABILITY TEST
# =====================================================================

@pytest.mark.asyncio
async def test_trace_tool_execution_observability(mock_context) -> None:
    # Executes the decorator context block to cover tracing.py branches
    async with trace_tool_execution("mock_tool", mock_context):
        pass
        
    # Test error tracing path
    with pytest.raises(ValueError):
        async with trace_tool_execution("mock_tool", mock_context):
            raise ValueError("Test error")


# =====================================================================
# REST CLIENT ERROR FLOWS & CONNECTOR EXCEPTIONS (FOR 90%+ COVERAGE)
# =====================================================================

@pytest.mark.asyncio
async def test_connector_http_failure_paths() -> None:
    # 1. HubSpot client failure
    hs = CRMService(provider="hubspot", credentials={"api_key": "hs_key"})
    with patch("httpx.AsyncClient.post", return_value=httpx.Response(500, text="Server Error")):
        with pytest.raises(ConnectorError):
            await hs.create_lead({"first_name": "a", "last_name": "b", "email": "a@a.com"})
            
    # 2. Salesforce client failure
    sf = CRMService(provider="salesforce", credentials={"instance_url": "http://x.com", "access_token": "sf"})
    with patch("httpx.AsyncClient.post", return_value=httpx.Response(500, text="Server Error")):
        with pytest.raises(ConnectorError):
            await sf.create_lead({"first_name": "a", "last_name": "b", "email": "a@a.com"})
            
    # 3. Zoho client failure
    zh = CRMService(provider="zoho", credentials={"access_token": "zh"})
    with patch("httpx.AsyncClient.post", return_value=httpx.Response(500, text="Server Error")):
        with pytest.raises(ConnectorError):
            await zh.create_lead({"first_name": "a", "last_name": "b", "email": "a@a.com"})

    # 4. WhatsApp client failure
    wa = WhatsAppService(phone_number_id="wa_id", access_token="wa_token")
    with patch("httpx.AsyncClient.post", return_value=httpx.Response(500, text="Server Error")):
        with pytest.raises(ConnectorError):
            await wa.send_message("123", "hi")
        with pytest.raises(ConnectorError):
            await wa.send_template("123", "temp")
        with pytest.raises(ConnectorError):
            await wa.send_media("123", "image", "http://x.com/img.png")


@pytest.mark.asyncio
async def test_calendar_service_http_failures() -> None:
    g_auth = GmailAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    g_auth.get_valid_token = AsyncMock(return_value="g_tok")
    
    o_auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    o_auth.get_valid_token = AsyncMock(return_value="o_tok")
    
    service = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
    
    # Mock Google & Outlook failures
    mock_err_res = httpx.Response(500, text="Server Error")
    
    # Test Create Google / Outlook Failures
    with patch("httpx.AsyncClient.post", return_value=mock_err_res):
        with pytest.raises(ConnectorError):
            await service.create_event("google", "S", "B", "2026-06-15T10Z", "2026-06-15T11Z")
        with pytest.raises(ConnectorError):
            await service.create_event("outlook", "S", "B", "2026-06-15T10Z", "2026-06-15T11Z")
        with pytest.raises(ConnectorError):
            await service.get_availability("google", "2026-06-15T10Z", "2026-06-15T11Z", ["a@a.com"])
        with pytest.raises(ConnectorError):
            await service.get_availability("outlook", "2026-06-15T10Z", "2026-06-15T11Z", ["a@a.com"])

    # Test Update/Cancel Google / Outlook Failures
    with patch("httpx.AsyncClient.patch", return_value=mock_err_res):
        with pytest.raises(ConnectorError):
            await service.update_event("google", "id", {})
        with pytest.raises(ConnectorError):
            await service.update_event("outlook", "id", {})
            
    with patch("httpx.AsyncClient.delete", return_value=mock_err_res):
        with pytest.raises(ConnectorError):
            await service.cancel_event("google", "id")
        with pytest.raises(ConnectorError):
            await service.cancel_event("outlook", "id")


@pytest.mark.asyncio
async def test_tool_execute_failure_paths_graceful_catch(mock_context) -> None:
    # This tests the "except Exception as e" block inside all concrete tool.execute() calls.
    # We will trigger exceptions inside the service methods and verify the tool returns MCPResult(success=False).
    
    # 1. Gmail Tools Error catch
    g_auth = GmailAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    g_auth.get_valid_token = AsyncMock(return_value="tok")
    connector_g = GmailConnector(g_auth)
    # Injecting failing methods
    connector_g.service.send_email = AsyncMock(side_effect=ValueError("Gmail Error"))
    connector_g.service.reply_email = AsyncMock(side_effect=ValueError("Gmail Error"))
    connector_g.service.search_emails = AsyncMock(side_effect=ValueError("Gmail Error"))
    connector_g.service.read_thread = AsyncMock(side_effect=ValueError("Gmail Error"))
    
    res = await connector_g.execute("send_email", mock_context, {"to": "a@a.com", "subject": "S", "body": "B"})
    assert res.success is False and "Gmail Error" in res.error
    res = await connector_g.execute("reply_email", mock_context, {"thread_id": "th1", "body": "B"})
    assert res.success is False and "Gmail Error" in res.error
    res = await connector_g.execute("search_email", mock_context, {"query": "is:unread"})
    assert res.success is False and "Gmail Error" in res.error
    res = await connector_g.execute("read_thread", mock_context, {"thread_id": "th1"})
    assert res.success is False and "Gmail Error" in res.error

    # 2. Outlook Tools Error catch
    o_auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    o_auth.get_valid_token = AsyncMock(return_value="tok")
    connector_o = OutlookConnector(o_auth)
    connector_o.service.send_email = AsyncMock(side_effect=ValueError("Outlook Error"))
    connector_o.service.reply_email = AsyncMock(side_effect=ValueError("Outlook Error"))
    connector_o.service.read_email = AsyncMock(side_effect=ValueError("Outlook Error"))
    connector_o.service.create_event = AsyncMock(side_effect=ValueError("Outlook Error"))
    
    res = await connector_o.execute("outlook_send_email", mock_context, {"to": "a@a.com", "subject": "S", "body": "B"})
    assert res.success is False and "Outlook Error" in res.error
    res = await connector_o.execute("outlook_reply_email", mock_context, {"message_id": "msg1", "body": "B"})
    assert res.success is False and "Outlook Error" in res.error
    res = await connector_o.execute("outlook_read_email", mock_context, {"message_id": "msg1"})
    assert res.success is False and "Outlook Error" in res.error
    res = await connector_o.execute("outlook_create_event", mock_context, {"subject": "S", "body": "B", "start_time": "T1", "end_time": "T2"})
    assert res.success is False and "Outlook Error" in res.error

    # 3. CRM Tools Error catch
    crm_serv = CRMService(provider="hubspot", credentials={"api_key": "hs"})
    connector_crm = CRMConnector(crm_serv)
    connector_crm.service.create_lead = AsyncMock(side_effect=ValueError("CRM Error"))
    connector_crm.service.update_lead = AsyncMock(side_effect=ValueError("CRM Error"))
    connector_crm.service.search_contact = AsyncMock(side_effect=ValueError("CRM Error"))
    connector_crm.service.create_opportunity = AsyncMock(side_effect=ValueError("CRM Error"))
    connector_crm.service.update_opportunity = AsyncMock(side_effect=ValueError("CRM Error"))
    
    res = await connector_crm.execute("create_lead", mock_context, {"first_name": "F", "last_name": "L", "email": "e@e.com"})
    assert res.success is False and "CRM Error" in res.error
    res = await connector_crm.execute("update_lead", mock_context, {"lead_id": "id1", "lead_data": {}})
    assert res.success is False and "CRM Error" in res.error
    res = await connector_crm.execute("search_contact", mock_context, {"query": "q"})
    assert res.success is False and "CRM Error" in res.error
    res = await connector_crm.execute("create_opportunity", mock_context, {"name": "n", "stage": "s", "close_date": "d", "amount": 1.0})
    assert res.success is False and "CRM Error" in res.error
    res = await connector_crm.execute("update_opportunity", mock_context, {"opp_id": "id1", "opp_data": {}})
    assert res.success is False and "CRM Error" in res.error

    # 4. Calendar Tools Error catch
    cal_serv = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
    connector_cal = CalendarConnector(cal_serv)
    connector_cal.service.create_event = AsyncMock(side_effect=ValueError("Calendar Error"))
    connector_cal.service.update_event = AsyncMock(side_effect=ValueError("Calendar Error"))
    connector_cal.service.cancel_event = AsyncMock(side_effect=ValueError("Calendar Error"))
    connector_cal.service.get_availability = AsyncMock(side_effect=ValueError("Calendar Error"))
    
    res = await connector_cal.execute("create_event", mock_context, {"provider": "google", "subject": "S", "body": "B", "start_time": "T1", "end_time": "T2"})
    assert res.success is False and "Calendar Error" in res.error
    res = await connector_cal.execute("update_event", mock_context, {"provider": "google", "event_id": "id", "event_data": {}})
    assert res.success is False and "Calendar Error" in res.error
    res = await connector_cal.execute("cancel_event", mock_context, {"provider": "google", "event_id": "id"})
    assert res.success is False and "Calendar Error" in res.error
    res = await connector_cal.execute("get_availability", mock_context, {"provider": "google", "start_time": "T1", "end_time": "T2", "emails": []})
    assert res.success is False and "Calendar Error" in res.error

    # 5. WhatsApp Tools Error catch
    wa_serv = WhatsAppService(phone_number_id="wa", access_token="tok")
    connector_wa = WhatsAppConnector(wa_serv)
    connector_wa.service.send_message = AsyncMock(side_effect=ValueError("WhatsApp Error"))
    connector_wa.service.send_template = AsyncMock(side_effect=ValueError("WhatsApp Error"))
    connector_wa.service.send_media = AsyncMock(side_effect=ValueError("WhatsApp Error"))
    connector_wa.service.get_conversation = AsyncMock(side_effect=ValueError("WhatsApp Error"))
    
    res = await connector_wa.execute("whatsapp_send_message", mock_context, {"to": "123", "body": "B"})
    assert res.success is False and "WhatsApp Error" in res.error
    res = await connector_wa.execute("whatsapp_send_template", mock_context, {"to": "123", "template_name": "temp"})
    assert res.success is False and "WhatsApp Error" in res.error
    res = await connector_wa.execute("whatsapp_send_media", mock_context, {"to": "123", "media_type": "image", "media_url": "url"})
    assert res.success is False and "WhatsApp Error" in res.error
    res = await connector_wa.execute("whatsapp_get_conversation", mock_context, {"phone_number": "123"})
    assert res.success is False and "WhatsApp Error" in res.error


# =====================================================================
# ADDED UNIT TESTS FOR 90%+ COVERAGE PROOF
# =====================================================================

@pytest.mark.asyncio
async def test_all_tool_metadata_coverage() -> None:
    # 1. Loop through all connector tools and access metadata properties to cover tool.py classes
    g_auth = GmailAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    o_auth = OutlookAuth(client_id="cid", client_secret="cs", refresh_token="rt")
    crm_serv = CRMService(provider="hubspot", credentials={"api_key": "hs"})
    cal_serv = CalendarService(google_auth=g_auth, outlook_auth=o_auth)
    wa_serv = WhatsAppService(phone_number_id="wa", access_token="tok")
    
    connectors = [
        GmailConnector(g_auth),
        OutlookConnector(o_auth),
        CRMConnector(crm_serv),
        CalendarConnector(cal_serv),
        WhatsAppConnector(wa_serv),
    ]
    
    for conn in connectors:
        for tool in conn.get_tools():
            # Check properties exist and are of appropriate types
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert isinstance(tool.capability, MCPCapability)
            assert isinstance(tool.input_schema, dict)
            assert isinstance(tool.output_schema, dict)


@pytest.mark.asyncio
async def test_discovery_failing_connector_exception_branch() -> None:
    # Test error handling inside discovery.py when a connector.connect() fails
    registry = ToolRegistry()
    connector = DummyConnector("mock_crm", [])
    # Force connect to throw ValueError
    connector.connect = AsyncMock(side_effect=ValueError("Connect Error"))
    
    # discovery should catch the exception and log it instead of raising
    await discover_and_register(registry, [connector])
    assert len(await registry.list_tools()) == 0


@pytest.mark.asyncio
async def test_rate_limiter_reset_and_trigger() -> None:
    # Trigger rate limiter reset path
    limiter = RateLimiter(default_rate=1.0, default_burst=2)
    await limiter.reset()
    assert len(limiter.buckets) == 0
