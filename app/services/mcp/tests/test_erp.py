"""Unit tests for ERP Connector Framework and adapters."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from mcp.base.context import MCPContext
from mcp.base.exceptions import ConnectorError
from mcp.erp.service import ERPService
from mcp.erp.connector import ERPConnector


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
async def test_sap_adapter_endpoints() -> None:
    service = ERPService(
        provider="sap",
        credentials={"base_url": "https://sap.local/api", "username": "usr", "password": "pwd"}
    )
    
    mock_res_ok = httpx.Response(201, json={"d": {"BusinessPartner": "100"}})
    with patch("httpx.AsyncClient.post", return_value=mock_res_ok):
        res = await service.create_customer({"name": "Test Customer"})
        assert res["BusinessPartner"] == "100"

    mock_patch_ok = httpx.Response(204)
    with patch("httpx.AsyncClient.patch", return_value=mock_patch_ok):
        res = await service.update_customer("100", {"name": "Test New"})
        assert res["status"] == "updated"

    mock_search = httpx.Response(200, json={"d": {"results": [{"BusinessPartner": "100"}]}})
    with patch("httpx.AsyncClient.get", return_value=mock_search):
        res = await service.search_customer("Test")
        assert len(res) == 1


@pytest.mark.asyncio
async def test_oracle_adapter_endpoints() -> None:
    service = ERPService(
        provider="oracle",
        credentials={"base_url": "https://netsuite.local/api", "token": "t1"}
    )
    
    mock_res_ok = httpx.Response(201, json={"id": "cust_101"})
    with patch("httpx.AsyncClient.post", return_value=mock_res_ok):
        res = await service.create_customer({"name": "Oracle Customer"})
        assert res["id"] == "cust_101"


@pytest.mark.asyncio
async def test_odoo_adapter_endpoints() -> None:
    service = ERPService(
        provider="odoo",
        credentials={"url": "https://odoo.local", "db": "db", "username": "usr", "password": "pwd"}
    )
    
    # Mock authentication session call, then read_kw call
    mock_auth_ok = httpx.Response(200, json={"result": 2}) # Returns uid=2
    mock_auth_ok.request = httpx.Request("POST", "https://odoo.local/jsonrpc")
    mock_execute_ok = httpx.Response(200, json={"result": 42}) # Created customer ID 42
    mock_execute_ok.request = httpx.Request("POST", "https://odoo.local/jsonrpc")
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = [mock_auth_ok, mock_execute_ok]
        res = await service.create_customer({"name": "Odoo Cust"})
        assert res["id"] == 42


@pytest.mark.asyncio
async def test_dynamics_adapter_endpoints() -> None:
    service = ERPService(
        provider="dynamics",
        credentials={"resource": "https://dynamics.local", "client_id": "cid", "client_secret": "cs"}
    )
    
    mock_auth_ok = httpx.Response(200, json={"access_token": "dyn_token"})
    mock_customer_ok = httpx.Response(201, json={"OrganizationName": "Dynamics Cust"})
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = [mock_auth_ok, mock_customer_ok]
        res = await service.create_customer({"name": "Dynamics Cust"})
        assert res["OrganizationName"] == "Dynamics Cust"


@pytest.mark.asyncio
async def test_erp_connector_routing(mock_context) -> None:
    service = ERPService(
        provider="sap",
        credentials={"base_url": "https://sap.local/api", "username": "usr", "password": "pwd"}
    )
    connector = ERPConnector(service)
    assert connector.name == "erp_sap"
    assert len(connector.get_tools()) == 10

    # Mock customer search for health check
    mock_search = httpx.Response(200, json={"d": {"results": []}})
    with patch("httpx.AsyncClient.get", return_value=mock_search):
        assert await connector.health_check() is True

    # Call customer search tool
    with patch("httpx.AsyncClient.get", return_value=mock_search):
        res = await connector.execute("erp_search_customer", mock_context, {"query": "test"})
        assert res.success is True
        assert len(res.data) == 0
