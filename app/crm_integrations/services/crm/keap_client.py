from app.crm_integrations.services.crm.base_client import BaseCRMClient


class KeapClient(BaseCRMClient):
    provider = "keap"
    display_name = "Keap"
    api_base_url = "https://api.infusionsoft.com"
