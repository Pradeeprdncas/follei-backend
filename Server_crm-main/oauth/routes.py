import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database.repository import CRMConnectionRepository, OAuthStateRepository
from oauth.registry import provider_registry
from oauth.crypto import CryptoUtil
from oauth.schemas import ConnectionStatus, RefreshResponse, DisconnectResponse
from oauth.token_manager import token_manager
from core.exceptions import CRMAuthException, CRMClientException, CRMAdapterNotFoundException

logger = logging.getLogger("crm_gateway.oauth.routes")
router = APIRouter(prefix="/oauth", tags=["OAuth"])
crypto = CryptoUtil()


@router.get("/{provider}/login")
async def login(
    provider: str,
    user_id: str = Query(..., description="ID of the user initiating the connection"),
    db: AsyncSession = Depends(get_db)
):
    """
    Initializes OAuth Authorization Flow:
    1. Generates a secure, random state token.
    2. Saves state locally for CSRF validation.
    3. Resolves the redirect URL for the provider and sends user there.
    """
    logger.info(f"OAuth login flow started: user_id='{user_id}', provider='{provider}'")
    try:
        oauth_provider = provider_registry.get(provider)
    except CRMAdapterNotFoundException as e:
        logger.error(f"Invalid provider requested: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    # Generate a cryptographically secure random state
    state = secrets.token_urlsafe(32)

    # Persist the state in the database with a 10-minute expiration
    state_repo = OAuthStateRepository(db)
    await state_repo.create_state(state=state, user_id=user_id, provider=provider, expires_in_seconds=600)
    await db.commit()

    # Generate the OAuth authorize URL
    auth_url = oauth_provider.get_authorization_url(state=state)
    logger.info(f"Redirecting user '{user_id}' to authorization URL for '{provider}'")
    return RedirectResponse(auth_url)


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth redirect callback handler:
    1. Validates the state parameter for CSRF mitigation.
    2. Exposes code to provider wrapper for token exchange.
    3. Encrypts tokens and persists them in DB.
    4. Renders interactive HTML success/failure response.
    """
    logger.info(f"OAuth callback received from provider '{provider}'")

    if error:
        msg = f"OAuth authorization denied by provider: {error_description or error}"
        logger.warning(msg)
        return HTMLResponse(content=_get_error_page(provider, msg), status_code=400)

    if not code or not state:
        msg = "Missing authorization code or state parameter."
        logger.warning(msg)
        return HTMLResponse(content=_get_error_page(provider, msg), status_code=400)

    # Validate state. validate_state deletes the record instantly, preventing replay attacks.
    state_repo = OAuthStateRepository(db)
    state_record = await state_repo.validate_state(state)
    if not state_record:
        msg = "Invalid or expired OAuth state parameter (state mismatch or session expired)."
        logger.warning(msg)
        return HTMLResponse(content=_get_error_page(provider, msg), status_code=400)

    user_id = state_record.user_id

    try:
        oauth_provider = provider_registry.get(provider)
        
        # Exchange authorization code for tokens
        exchange_res = await oauth_provider.exchange_code(code)

        # Encrypt the access and refresh tokens before storing
        enc_access = crypto.encrypt(exchange_res["access_token"])
        enc_refresh = crypto.encrypt(exchange_res["refresh_token"])

        # Calculate expires_at timestamp
        expires_in = exchange_res["expires_in"]
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Save to database
        conn_repo = CRMConnectionRepository(db)
        await conn_repo.save_connection(
            user_id=user_id,
            provider=provider,
            access_token=enc_access,
            refresh_token=enc_refresh,
            expires_at=expires_at,
            scopes=exchange_res.get("scopes"),
            account_id=exchange_res.get("account_id"),
            account_name=exchange_res.get("account_name"),
            metadata=exchange_res.get("metadata")
        )
        await db.commit()

        logger.info(f"Successfully integrated '{provider}' for user_id='{user_id}'")
        return HTMLResponse(content=_get_success_page(provider, exchange_res.get("account_name")))

    except (CRMAuthException, CRMClientException) as e:
        logger.error(f"OAuth exchange failed: {str(e)}")
        await db.rollback()
        return HTMLResponse(content=_get_error_page(provider, f"Integration failed: {str(e)}"), status_code=400)
    except Exception as e:
        logger.exception("Unexpected error occurred in callback workflow")
        await db.rollback()
        return HTMLResponse(content=_get_error_page(provider, f"Internal system failure: {str(e)}"), status_code=500)


@router.post("/{provider}/refresh", response_model=RefreshResponse)
async def refresh(
    provider: str,
    user_id: str = Query(..., description="ID of the user whose connection to refresh"),
    db: AsyncSession = Depends(get_db)
):
    """
    Force updates the CRM connection tokens by invoking the TokenManager.
    Uses large buffer to ensure refresh executes immediately.
    """
    logger.info(f"Manual token refresh requested for user_id='{user_id}', provider='{provider}'")
    try:
        # A huge buffer (10 years) guarantees expiration is hit and triggers the refresh flow
        await token_manager.get_valid_access_token(
            session=db,
            user_id=user_id,
            provider=provider,
            expiry_buffer_seconds=315360000  # 10 years
        )
        # Commit changes written by TokenManager
        await db.commit()
        logger.info(f"Manual token refresh succeeded for user_id='{user_id}', provider='{provider}'")
        return RefreshResponse(
            provider=provider,
            user_id=user_id,
            status="success",
            message="Access token successfully refreshed."
        )
    except CRMAuthException as e:
        logger.error(f"Unauthorized refresh: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during refresh")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


@router.delete("/{provider}/disconnect", response_model=DisconnectResponse)
async def disconnect(
    provider: str,
    user_id: str = Query(..., description="ID of the user to disconnect"),
    db: AsyncSession = Depends(get_db)
):
    """
    Disconnects the CRM Integration:
    1. Revokes the tokens at the CRM provider if supported.
    2. Deletes the database record.
    """
    logger.info(f"Disconnect requested for user_id='{user_id}', provider='{provider}'")
    try:
        oauth_provider = provider_registry.get(provider)
    except CRMAdapterNotFoundException as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn_repo = CRMConnectionRepository(db)
    conn = await conn_repo.get_connection(user_id, provider)

    if not conn:
        raise HTTPException(
            status_code=404, 
            detail=f"No connection found for user '{user_id}' and provider '{provider}'."
        )

    # Revoke tokens remotely on best-effort basis
    try:
        decrypted_access = crypto.decrypt(conn.access_token)
        if decrypted_access:
            await oauth_provider.revoke_token(decrypted_access)
            
        decrypted_refresh = crypto.decrypt(conn.refresh_token)
        if decrypted_refresh:
            await oauth_provider.revoke_token(decrypted_refresh)
    except Exception as e:
        logger.warning(f"CRM Provider token revocation failed: {str(e)}")

    # Delete connection record locally
    deleted = await conn_repo.delete_connection(user_id, provider)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to purge connection details.")

    await db.commit()
    logger.info(f"Successfully disconnected provider '{provider}' for user '{user_id}'")
    return DisconnectResponse(
        provider=provider,
        user_id=user_id,
        status="disconnected",
        message=f"Successfully disconnected from {provider.capitalize()}."
    )


@router.get("/{provider}/status", response_model=ConnectionStatus)
async def status_route(
    provider: str,
    user_id: str = Query(..., description="ID of the user whose status to check"),
    db: AsyncSession = Depends(get_db)
):
    """
    Checks the status of the connection without exposing secrets.
    """
    logger.info(f"Status check requested: user_id='{user_id}', provider='{provider}'")

    conn_repo = CRMConnectionRepository(db)
    conn = await conn_repo.get_connection(user_id, provider)

    if not conn:
        return ConnectionStatus(
            provider=provider,
            user_id=user_id,
            is_connected=False
        )

    scopes_list = None
    if conn.scopes:
        scopes_list = conn.scopes.replace(",", " ").split()

    return ConnectionStatus(
        provider=conn.provider,
        user_id=conn.user_id,
        is_connected=True,
        account_id=conn.account_id,
        account_name=conn.account_name,
        scopes=scopes_list,
        expires_at=conn.expires_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at
    )


def _get_success_page(provider: str, account_name: str | None) -> str:
    """Beautiful, interactive HTML page shown to user upon successful connection."""
    account_desc = f"({account_name})" if account_name else ""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connection Successful</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                font-family: 'Outfit', sans-serif;
                color: #f8fafc;
            }}
            .card {{
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                padding: 48px;
                width: 100%;
                max-width: 450px;
                text-align: center;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                animation: fadeIn 0.8s ease-out;
            }}
            .icon-wrapper {{
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
                animation: popIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
            }}
            .icon {{
                color: white;
                font-size: 40px;
                font-weight: bold;
            }}
            h1 {{
                font-size: 28px;
                font-weight: 800;
                margin: 0 0 12px;
                background: linear-gradient(to right, #f8fafc, #cbd5e1);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            p {{
                font-size: 16px;
                color: #94a3b8;
                line-height: 1.6;
                margin: 0 0 32px;
            }}
            .badge {{
                display: inline-block;
                background: rgba(16, 185, 129, 0.15);
                border: 1px solid rgba(16, 185, 129, 0.3);
                color: #34d399;
                padding: 8px 16px;
                border-radius: 9999px;
                font-weight: 600;
                font-size: 14px;
                margin-bottom: 24px;
            }}
            .close-btn {{
                background: linear-gradient(to right, #4f46e5, #6366f1);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 14px 28px;
                font-weight: 600;
                font-size: 16px;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            }}
            .close-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
            }}
            .close-btn:active {{
                transform: translateY(0);
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            @keyframes popIn {{
                from {{ transform: scale(0.5); opacity: 0; }}
                to {{ transform: scale(1); opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-wrapper">
                <span class="icon">&check;</span>
            </div>
            <h1>Connection Successful!</h1>
            <div class="badge">{provider.capitalize()} Connected {account_desc}</div>
            <p>Your CRM account has been securely integrated with the CRM Gateway. You can now close this tab and return to your application.</p>
            <button class="close-btn" onclick="window.close()">Close Window</button>
        </div>
    </body>
    </html>
    """


def _get_error_page(provider: str, message: str) -> str:
    """Beautiful, interactive HTML page shown to user upon failed connection."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connection Failed</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                font-family: 'Outfit', sans-serif;
                color: #f8fafc;
            }}
            .card {{
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                padding: 48px;
                width: 100%;
                max-width: 450px;
                text-align: center;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                animation: fadeIn 0.8s ease-out;
            }}
            .icon-wrapper {{
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                box-shadow: 0 0 20px rgba(239, 68, 68, 0.4);
                animation: popIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
            }}
            .icon {{
                color: white;
                font-size: 40px;
                font-weight: bold;
            }}
            h1 {{
                font-size: 28px;
                font-weight: 800;
                margin: 0 0 12px;
                background: linear-gradient(to right, #f8fafc, #cbd5e1);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            p {{
                font-size: 16px;
                color: #94a3b8;
                line-height: 1.6;
                margin: 0 0 32px;
            }}
            .badge {{
                display: inline-block;
                background: rgba(239, 68, 68, 0.15);
                border: 1px solid rgba(239, 68, 68, 0.3);
                color: #f87171;
                padding: 8px 16px;
                border-radius: 9999px;
                font-weight: 600;
                font-size: 14px;
                margin-bottom: 24px;
            }}
            .close-btn {{
                background: linear-gradient(to right, #4b5563, #6b7280);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 14px 28px;
                font-weight: 600;
                font-size: 16px;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .close-btn:hover {{
                transform: translateY(-2px);
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            @keyframes popIn {{
                from {{ transform: scale(0.5); opacity: 0; }}
                to {{ transform: scale(1); opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-wrapper">
                <span class="icon">&times;</span>
            </div>
            <h1>Connection Failed</h1>
            <div class="badge">Integration Error</div>
            <p>{message}</p>
            <button class="close-btn" onclick="window.close()">Close Window</button>
        </div>
    </body>
    </html>
    """
