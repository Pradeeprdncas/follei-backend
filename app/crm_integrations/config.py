from dataclasses import dataclass

from app.config.settings import get_settings


_s = get_settings()


@dataclass(frozen=True)
class Settings:
    app_name: str = "crm-integrations"
    environment: str = _s.APP_ENV
    encryption_key: str = _s.CRM_ENCRYPTION_KEY
    frontend_base_url: str = _s.FRONTEND_BASE_URL
    frontend_crm_return_path: str = _s.FRONTEND_CRM_RETURN_PATH
    api_base_url: str = "http://localhost:8000"
    cors_origins: list[str] | None = None

    salesforce_client_id: str = _s.SALESFORCE_CLIENT_ID
    salesforce_client_secret: str = _s.SALESFORCE_CLIENT_SECRET
    hubspot_client_id: str = _s.HUBSPOT_CLIENT_ID
    hubspot_client_secret: str = _s.HUBSPOT_CLIENT_SECRET
    zoho_client_id: str = _s.ZOHO_CLIENT_ID
    zoho_client_secret: str = _s.ZOHO_CLIENT_SECRET
    zoho_accounts_domain: str = _s.ZOHO_ACCOUNTS_DOMAIN
    microsoft_client_id: str = _s.MICROSOFT_CLIENT_ID
    microsoft_client_secret: str = _s.MICROSOFT_CLIENT_SECRET
    microsoft_tenant: str = _s.MICROSOFT_TENANT
    pipedrive_client_id: str = _s.PIPEDRIVE_CLIENT_ID
    pipedrive_client_secret: str = _s.PIPEDRIVE_CLIENT_SECRET
    freshsales_client_id: str = _s.FRESHSALES_CLIENT_ID
    freshsales_client_secret: str = _s.FRESHSALES_CLIENT_SECRET
    freshsales_accounts_domain: str = _s.FRESHSALES_ACCOUNTS_DOMAIN
    copper_client_id: str = _s.COPPER_CLIENT_ID
    copper_client_secret: str = _s.COPPER_CLIENT_SECRET
    keap_client_id: str = _s.KEAP_CLIENT_ID
    keap_client_secret: str = _s.KEAP_CLIENT_SECRET


settings = Settings()
