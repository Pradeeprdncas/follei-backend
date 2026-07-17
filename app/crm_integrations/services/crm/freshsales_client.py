from app.crm_integrations.services.crm.base_client import BaseCRMClient


class FreshsalesClient(BaseCRMClient):
    provider = "freshsales"
    display_name = "Freshsales"
    api_base_url = "https://api.freshsales.io"
