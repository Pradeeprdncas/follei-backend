
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.adapter import CRMAdapter
from database.connection import init_db, get_db
from oauth.token_manager import token_manager
from oauth.routes import router as oauth_router
from core.factory import AdapterFactory
from core.exceptions import (
    CRMAuthException,
    CRMClientException,
    CRMConnectionException,
    CRMObjectNotFoundException,
    CRMRateLimitException,
    CRMAdapterNotFoundException,
    CRMValidationException,
)
from models.schemas import (
    Company,
    CompanyCreate,
    CompanyUpdate,
    Contact,
    ContactCreate,
    ContactUpdate,
    Deal,
    DealCreate,
    DealUpdate,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application resource lifecycle (HTTP client pooling and DB tables)."""
    # Initialize database tables
    await init_db()
    # Create a single reusable httpx AsyncClient for connection pooling
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    # Clean up the pooled HTTP client
    await app.state.http_client.aclose()


app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# Register OAuth endpoints router
app.include_router(oauth_router)


# --- EXCEPTION HANDLERS ---

@app.exception_handler(CRMObjectNotFoundException)
async def object_not_found_handler(request: Request, exc: CRMObjectNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "status": 404, "error_type": "ObjectNotFound"},
    )


@app.exception_handler(CRMAuthException)
async def auth_exception_handler(request: Request, exc: CRMAuthException):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc), "status": 401, "error_type": "Unauthorized"},
    )


@app.exception_handler(CRMRateLimitException)
async def rate_limit_handler(request: Request, exc: CRMRateLimitException):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(exc), "status": 429, "error_type": "RateLimited"},
    )


@app.exception_handler(CRMConnectionException)
async def connection_handler(request: Request, exc: CRMConnectionException):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "status": 503, "error_type": "ConnectionError"},
    )


@app.exception_handler(CRMAdapterNotFoundException)
async def adapter_not_found_handler(request: Request, exc: CRMAdapterNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "status": 400, "error_type": "UnsupportedProvider"},
    )


@app.exception_handler(CRMClientException)
async def client_exception_handler(request: Request, exc: CRMClientException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": str(exc),
            "status": 400,
            "error_type": "ClientError",
            "body": exc.response_body,
        },
    )



async def get_crm_adapter(
    x_crm_provider: str = Header(..., alias="X-CRM-Provider", description="Name of the CRM provider"),
    x_crm_token: Optional[str] = Header(None, alias="X-CRM-Token", description="Authorization Bearer Token"),
    x_crm_base_url: Optional[str] = Header(None, alias="X-CRM-Base-URL", description="Base URL of target CRM instance"),
    x_crm_auth_type: Optional[str] = Header(None, alias="X-CRM-Auth-Type", description="Auth strategy (oauth2, basic, api_key_header, api_key_query)"),
    x_crm_api_key: Optional[str] = Header(None, alias="X-CRM-API-Key", description="API Key for API Key strategies"),
    x_crm_username: Optional[str] = Header(None, alias="X-CRM-Username", description="Username for Basic authentication"),
    x_crm_password: Optional[str] = Header(None, alias="X-CRM-Password", description="Password for Basic authentication"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID", description="User ID for dynamic OAuth flow resolution"),
    db: AsyncSession = Depends(get_db),
) -> CRMAdapter:
    """
    Extracts authentication headers and yields a configured CRMAdapter.
    Uses default settings from config.py if headers are omitted for verification.
    """
    provider = x_crm_provider.strip().lower()

    # Fallback to defaults defined in settings
    base_url = x_crm_base_url
    if not base_url:
        if provider == "hubspot":
            base_url = settings.HUBSPOT_BASE_URL
        elif provider == "zoho":
            base_url = settings.ZOHO_BASE_URL
        elif provider == "salesforce":
            base_url = settings.SALESFORCE_BASE_URL
        else:
            raise HTTPException(status_code=400, detail=f"Base URL not provided and no default configured for '{provider}'")

    auth_type = (x_crm_auth_type or "oauth2").lower()
    credentials = {
        "baseURL": base_url,
        "auth_type": auth_type,
    }

    if auth_type == "oauth2":
        if x_user_id and not x_crm_token:
            # Bind dynamic token load properties
            credentials.update({
                "user_id": x_user_id,
                "provider": provider,
                "token_manager": token_manager,
                "db_session": db,
            })
        else:
            token = x_crm_token
            if not token:
                if provider == "hubspot":
                    token = settings.HUBSPOT_TOKEN
                elif provider == "zoho":
                    token = settings.ZOHO_TOKEN
                elif provider == "salesforce":
                    token = settings.SALESFORCE_TOKEN
            credentials["token"] = token
        
    elif auth_type in ("api_key_header", "api_key_query"):
        credentials["api_key"] = x_crm_api_key or x_crm_token
        
    elif auth_type == "basic":
        credentials["username"] = x_crm_username
        credentials["password"] = x_crm_password or ""

    try:
        # Resolve the adapter injecting the app-wide pooled HTTP client
        return AdapterFactory.create(
            crm=provider,
            credentials=credentials,
            http_client=app.state.http_client
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to instantiate CRM Adapter: {str(e)}")




@app.get("/contacts", response_model=List[Contact], tags=["Contacts"])
async def get_contacts(
    limit: int = 100,
    after: Optional[str] = None,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    return await adapter.get_contacts(limit=limit, after=after)


@app.get("/contacts/{contact_id}", response_model=Contact, tags=["Contacts"])
async def get_contact(
    contact_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    return await adapter.get_contact(contact_id=contact_id)


@app.post("/contacts/search", response_model=List[Contact], tags=["Contacts"])
async def search_contacts(
    filters: Dict[str, Any],
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Search for contacts matching specified filters."""
    return await adapter.search_contacts(filters=filters)


@app.post("/contacts", response_model=Contact, status_code=status.HTTP_201_CREATED, tags=["Contacts"])
async def create_contact(
    contact: ContactCreate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Create a new contact."""
    return await adapter.create_contact(contact=contact)


@app.patch("/contacts/{contact_id}", response_model=Contact, tags=["Contacts"])
async def update_contact(
    contact_id: str,
    contact: ContactUpdate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Update properties of an existing contact."""
    return await adapter.update_contact(contact_id=contact_id, contact=contact)


@app.delete("/contacts/{contact_id}", tags=["Contacts"])
async def delete_contact(
    contact_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Delete a contact."""
    success = await adapter.delete_contact(contact_id=contact_id)
    return {"success": success, "id": contact_id}


# --- COMPANIES ENDPOINTS ---

@app.get("/companies", response_model=List[Company], tags=["Companies"])
async def get_companies(
    limit: int = 100,
    after: Optional[str] = None,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Retrieve list of companies with pagination support."""
    return await adapter.get_companies(limit=limit, after=after)


@app.get("/companies/{company_id}", response_model=Company, tags=["Companies"])
async def get_company(
    company_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Retrieve a single company by ID."""
    return await adapter.get_company(company_id=company_id)


@app.post("/companies", response_model=Company, status_code=status.HTTP_201_CREATED, tags=["Companies"])
async def create_company(
    company: CompanyCreate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Create a new company."""
    return await adapter.create_company(company=company)


@app.patch("/companies/{company_id}", response_model=Company, tags=["Companies"])
async def update_company(
    company_id: str,
    company: CompanyUpdate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Update properties of an existing company."""
    return await adapter.update_company(company_id=company_id, company=company)


@app.delete("/companies/{company_id}", tags=["Companies"])
async def delete_company(
    company_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Delete a company."""
    success = await adapter.delete_company(company_id=company_id)
    return {"success": success, "id": company_id}


# --- DEALS ENDPOINTS ---

@app.get("/deals", response_model=List[Deal], tags=["Deals"])
async def get_deals(
    limit: int = 100,
    after: Optional[str] = None,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Retrieve list of deals with pagination support."""
    return await adapter.get_deals(limit=limit, after=after)


@app.get("/deals/{deal_id}", response_model=Deal, tags=["Deals"])
async def get_deal(
    deal_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Retrieve a single deal by ID."""
    return await adapter.get_deal(deal_id=deal_id)


@app.post("/deals", response_model=Deal, status_code=status.HTTP_201_CREATED, tags=["Deals"])
async def create_deal(
    deal: DealCreate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Create a new deal."""
    return await adapter.create_deal(deal=deal)


@app.patch("/deals/{deal_id}", response_model=Deal, tags=["Deals"])
async def update_deal(
    deal_id: str,
    deal: DealUpdate,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Update properties of an existing deal."""
    return await adapter.update_deal(deal_id=deal_id, deal=deal)


@app.delete("/deals/{deal_id}", tags=["Deals"])
async def delete_deal(
    deal_id: str,
    adapter: CRMAdapter = Depends(get_crm_adapter)
):
    """Delete a deal."""
    success = await adapter.delete_deal(deal_id=deal_id)
    return {"success": success, "id": deal_id}
