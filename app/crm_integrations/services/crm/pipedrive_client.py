from app.crm_integrations.services.crm.base_client import BaseCRMClient


class PipedriveClient(BaseCRMClient):
    provider = "pipedrive"
    display_name = "Pipedrive"
    api_base_url = "https://api.pipedrive.com"
