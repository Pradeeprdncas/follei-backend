from app.crm_integrations.services.crm.base_client import BaseCRMClient
from app.crm_integrations.services.crm.copper_client import CopperClient
from app.crm_integrations.services.crm.freshsales_client import FreshsalesClient
from app.crm_integrations.services.crm.hubspot_client import HubSpotClient
from app.crm_integrations.services.crm.insightly_client import InsightlyClient
from app.crm_integrations.services.crm.keap_client import KeapClient
from app.crm_integrations.services.crm.microsoft_d365_client import MicrosoftD365Client
from app.crm_integrations.services.crm.pipedrive_client import PipedriveClient
from app.crm_integrations.services.crm.salesforce_client import SalesforceClient
from app.crm_integrations.services.crm.zoho_client import ZohoClient


class CRMFactory:
    clients: dict[str, type[BaseCRMClient]] = {
        "salesforce": SalesforceClient,
        "hubspot": HubSpotClient,
        "zoho": ZohoClient,
        "pipedrive": PipedriveClient,
        "microsoft_d365": MicrosoftD365Client,
        "freshsales": FreshsalesClient,
        "copper": CopperClient,
        "insightly": InsightlyClient,
        "keap": KeapClient,
    }

    @classmethod
    def create(cls, provider: str, access_token: str | None = None, api_key: str | None = None) -> BaseCRMClient:
        client_class = cls.clients.get(provider)
        if not client_class:
            raise ValueError(f"Unsupported CRM provider: {provider}")
        return client_class(access_token=access_token, api_key=api_key)

    @classmethod
    def supported_providers(cls) -> list[str]:
        return list(cls.clients.keys())
