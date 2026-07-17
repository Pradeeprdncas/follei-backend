from app.crm_integrations.services.crm.base_client import BaseCRMClient


class MicrosoftD365Client(BaseCRMClient):
    provider = "microsoft_d365"
    display_name = "Microsoft D365"
    api_base_url = "https://graph.microsoft.com"
