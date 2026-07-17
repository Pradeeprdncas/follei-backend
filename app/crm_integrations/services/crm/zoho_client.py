from app.crm_integrations.services.crm.base_client import BaseCRMClient


class ZohoClient(BaseCRMClient):
    provider = "zoho"
    display_name = "Zoho CRM"
    api_base_url = "https://www.zohoapis.com"
