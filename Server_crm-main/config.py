"""
Gateway Configuration settings.
Loads environment variables and validates default settings.
"""
import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings:
    """System settings holder."""
    
    # Environment status
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

    # FastAPI settings
    API_TITLE: str = "CRM Gateway API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "Production-ready CRM Gateway integrating HubSpot, Zoho, and Salesforce."

    # Default Mock / Real credentials for verification & local dev
    # (Clients can also pass credentials dynamically in headers)
    
    # HubSpot Config
    HUBSPOT_BASE_URL: str = os.getenv("HUBSPOT_BASE_URL", "https://api.hubapi.com")
    HUBSPOT_TOKEN: str = os.getenv("HUBSPOT_TOKEN", "dummy-hubspot-token")

    # HubSpot OAuth Credentials
    HUBSPOT_CLIENT_ID: str = os.getenv("HUBSPOT_CLIENT_ID", "dummy-client-id")
    HUBSPOT_CLIENT_SECRET: str = os.getenv("HUBSPOT_CLIENT_SECRET", "dummy-client-secret")
    HUBSPOT_REDIRECT_URI: str = os.getenv("HUBSPOT_REDIRECT_URI", "http://localhost:8000/oauth/hubspot/callback")
    HUBSPOT_SCOPES: str = os.getenv("HUBSPOT_SCOPES", "crm.objects.contacts.read crm.objects.contacts.write crm.objects.companies.read crm.objects.companies.write crm.objects.deals.read crm.objects.deals.write")

    # Zoho Config
    ZOHO_BASE_URL: str = os.getenv("ZOHO_BASE_URL", "https://www.zohoapis.com")
    ZOHO_TOKEN: str = os.getenv("ZOHO_TOKEN", "dummy-zoho-token")

    # Salesforce Config
    SALESFORCE_BASE_URL: str = os.getenv("SALESFORCE_BASE_URL", "https://login.salesforce.com")
    SALESFORCE_TOKEN: str = os.getenv("SALESFORCE_TOKEN", "dummy-salesforce-token")

    # Crypto and Database Config
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./crm_gateway.db")


settings = Settings()

