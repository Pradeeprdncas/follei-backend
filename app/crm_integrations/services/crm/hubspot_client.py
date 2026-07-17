from app.crm_integrations.services.crm.base_client import BaseCRMClient


class HubSpotClient(BaseCRMClient):
    provider = "hubspot"
    display_name = "HubSpot CRM"
    api_base_url = "https://api.hubapi.com"
