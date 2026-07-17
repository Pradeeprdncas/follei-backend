from app.crm_integrations.services.crm.base_client import BaseCRMClient


class SalesforceClient(BaseCRMClient):
    provider = "salesforce"
    display_name = "Salesforce"
    api_base_url = "https://login.salesforce.com"
