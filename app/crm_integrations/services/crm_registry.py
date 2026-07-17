from dataclasses import dataclass, field
from app.crm_integrations.config import settings


@dataclass(frozen=True)
class CRMRegistryEntry:
    id: str
    name: str
    provider: str
    description: str
    category: str
    icon: str
    logo: str
    website: str
    oauth: bool
    supports: list[str]
    features: dict[str, bool]
    default_scopes: list[str] = field(default_factory=list)
    authorize_url: str | None = None
    token_url: str | None = None
    client_id_attr: str | None = None
    client_secret_attr: str | None = None
    extra_params: dict[str, str] = field(default_factory=dict)


def _zoho_accounts_base() -> str:
    domain = settings.zoho_accounts_domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"https://{domain}"


def _microsoft_oauth_base() -> str:
    tenant = settings.microsoft_tenant.strip() or "common"
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


def _freshsales_oauth_base() -> str:
    return settings.freshsales_accounts_domain.strip().rstrip("/")


CRM_REGISTRY: tuple[CRMRegistryEntry, ...] = (
    CRMRegistryEntry(id="salesforce", name="Salesforce", provider="salesforce", description="Cloud CRM for sales, service, marketing, and customer data.", category="CRM", icon="/static/icons/salesforce.svg", logo="/static/logos/salesforce.png", website="https://www.salesforce.com", oauth=True, supports=["contacts", "accounts", "leads", "deals"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, default_scopes=["api", "refresh_token"], authorize_url="https://login.salesforce.com/services/oauth2/authorize", token_url="https://login.salesforce.com/services/oauth2/token", client_id_attr="salesforce_client_id", client_secret_attr="salesforce_client_secret", extra_params={"prompt": "consent"}),
    CRMRegistryEntry(id="hubspot", name="HubSpot CRM", provider="hubspot", description="CRM for sales, marketing, and customer service.", category="CRM", icon="/static/icons/hubspot.svg", logo="/static/logos/hubspot.png", website="https://www.hubspot.com", oauth=True, supports=["contacts", "companies", "deals"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, default_scopes=["crm.objects.contacts.read", "crm.objects.contacts.write"], authorize_url="https://app.hubspot.com/oauth/authorize", token_url="https://api.hubapi.com/oauth/v1/token", client_id_attr="hubspot_client_id", client_secret_attr="hubspot_client_secret"),
    CRMRegistryEntry(id="zoho", name="Zoho CRM", provider="zoho", description="CRM platform for pipeline, sales automation, and customer engagement.", category="CRM", icon="/static/icons/zoho.svg", logo="/static/logos/zoho.png", website="https://www.zoho.com/crm", oauth=True, supports=["contacts", "accounts", "leads", "deals", "settings"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, default_scopes=["ZohoCRM.modules.ALL", "ZohoCRM.settings.ALL"], authorize_url=f"{_zoho_accounts_base()}/oauth/v2/auth", token_url=f"{_zoho_accounts_base()}/oauth/v2/token", client_id_attr="zoho_client_id", client_secret_attr="zoho_client_secret", extra_params={"access_type": "offline", "prompt": "consent"}),
    CRMRegistryEntry(id="pipedrive", name="Pipedrive", provider="pipedrive", description="Sales CRM focused on pipeline tracking and deal management.", category="CRM", icon="/static/icons/pipedrive.svg", logo="/static/logos/pipedrive.png", website="https://www.pipedrive.com", oauth=True, supports=["contacts", "companies", "deals", "activities"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, authorize_url="https://oauth.pipedrive.com/oauth/authorize", token_url="https://oauth.pipedrive.com/oauth/token", client_id_attr="pipedrive_client_id", client_secret_attr="pipedrive_client_secret"),
    CRMRegistryEntry(id="microsoft_d365", name="Microsoft D365", provider="microsoft_d365", description="Microsoft Dynamics 365 CRM and customer engagement platform.", category="CRM", icon="/static/icons/microsoft_d365.svg", logo="/static/logos/microsoft_d365.png", website="https://dynamics.microsoft.com", oauth=True, supports=["contacts", "accounts", "leads", "opportunities"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, default_scopes=["https://graph.microsoft.com/.default", "offline_access"], authorize_url=f"{_microsoft_oauth_base()}/authorize", token_url=f"{_microsoft_oauth_base()}/token", client_id_attr="microsoft_client_id", client_secret_attr="microsoft_client_secret", extra_params={"prompt": "consent"}),
    CRMRegistryEntry(id="freshsales", name="Freshsales", provider="freshsales", description="Freshworks CRM for sales automation, contacts, and deals.", category="CRM", icon="/static/icons/freshsales.svg", logo="/static/logos/freshsales.png", website="https://www.freshworks.com/crm/sales", oauth=True, supports=["contacts", "accounts", "leads", "deals"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, authorize_url=f"{_freshsales_oauth_base()}/oauth/authorize" if _freshsales_oauth_base() else None, token_url=f"{_freshsales_oauth_base()}/oauth/token" if _freshsales_oauth_base() else None, client_id_attr="freshsales_client_id", client_secret_attr="freshsales_client_secret"),
    CRMRegistryEntry(id="copper", name="Copper CRM", provider="copper", description="CRM built for Google Workspace teams and relationship management.", category="CRM", icon="/static/icons/copper.svg", logo="/static/logos/copper.png", website="https://www.copper.com", oauth=True, supports=["contacts", "companies", "opportunities", "tasks"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, authorize_url="https://app.copper.com/oauth/authorize", token_url="https://api.copper.com/oauth/token", client_id_attr="copper_client_id", client_secret_attr="copper_client_secret"),
    CRMRegistryEntry(id="insightly", name="Insightly CRM", provider="insightly", description="CRM for contact, opportunity, project, and workflow management.", category="CRM", icon="/static/icons/insightly.svg", logo="/static/logos/insightly.png", website="https://www.insightly.com", oauth=False, supports=["contacts", "organizations", "leads", "opportunities"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": False}),
    CRMRegistryEntry(id="keap", name="Keap", provider="keap", description="CRM and marketing automation for small businesses.", category="CRM", icon="/static/icons/keap.svg", logo="/static/logos/keap.png", website="https://keap.com", oauth=True, supports=["contacts", "companies", "opportunities", "tasks"], features={"auto_sync": True, "allow_collaboration": True, "refresh_tokens": True}, default_scopes=["full"], authorize_url="https://accounts.infusionsoft.com/app/oauth/authorize", token_url="https://api.infusionsoft.com/token", client_id_attr="keap_client_id", client_secret_attr="keap_client_secret"),
)


def list_crm_registry() -> tuple[CRMRegistryEntry, ...]:
    return CRM_REGISTRY


def get_crm_provider(provider: str) -> CRMRegistryEntry | None:
    return next((item for item in CRM_REGISTRY if item.id == provider), None)
