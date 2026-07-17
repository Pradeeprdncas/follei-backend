from app.crm_integrations.services.crm.base_client import BaseCRMClient


class InsightlyClient(BaseCRMClient):
    provider = "insightly"
    display_name = "Insightly CRM"
    api_base_url = "https://api.insightly.com"
