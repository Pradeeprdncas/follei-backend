"""
Generic CRM-Agnostic HTTP Client.
Wraps httpx.AsyncClient to manage connection reuse, automatic header merging,
query parameter construction, HTTP error mapping, and retry logic.
"""
import asyncio
import logging
from typing import Any, Dict, List

import httpx

from core.auth import BaseAuthStrategy, OAuth2BearerAuth
from core.exceptions import (
    CRMAuthException,
    CRMClientException,
    CRMConnectionException,
    CRMObjectNotFoundException,
    CRMRateLimitException,
)

logger = logging.getLogger("crm_gateway.client")


class GenericClient:
    """
    Generic HTTP client for CRM APIs.
    Maintains compatibility with original signature while adding robust features.
    """

    def __init__(
        self,
        baseURL: str,
        token: str | None = None,
        auth_strategy: BaseAuthStrategy | None = None,
        default_headers: Dict[str, str] | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        user_id: str | None = None,
        provider: str | None = None,
        token_manager: Any | None = None,
        db_session: Any | None = None,
    ):
        """
        Initialize the Generic Client.
        
        :param baseURL: Base URL for CRM endpoints.
        :param token: Legacy token (automatically converted to OAuth2BearerAuth).
        :param auth_strategy: Concrete pluggable auth strategy.
        :param default_headers: Headers sent on all requests.
        :param timeout: Connection timeout in seconds.
        :param client: Optional pre-configured httpx.AsyncClient for connection reuse.
        :param user_id: ID of the user owning this CRM connection.
        :param provider: CRM provider name.
        :param token_manager: Reusable token manager.
        :param db_session: Active database session.
        """
        self.baseURL = baseURL.rstrip("/")
        self.user_id = user_id
        self.provider = provider
        self.token_manager = token_manager
        self.db_session = db_session
        
        # Backward compatibility layer
        if auth_strategy is None:
            if token is not None:
                auth_strategy = OAuth2BearerAuth(token)
            else:
                # If neither is passed, use a placeholder strategy (anonymous/empty auth)
                class AnonymousAuth(BaseAuthStrategy):
                    pass
                auth_strategy = AnonymousAuth()
        else:
            # Sync token for backward compatibility if strategy is OAuth2BearerAuth
            if isinstance(auth_strategy, OAuth2BearerAuth) and token is None:
                token = auth_strategy.token

        self.auth_strategy = auth_strategy
        self.token = token  # Keep attribute for backward compatibility
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self._client = client
        self._own_client = False


    @property
    def headers(self) -> Dict[str, str]:
        """Backward-compatible headers property."""
        return self._prepare_headers()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or initialize the HTTP client (ensuring connection pooling)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._own_client = True
        return self._client

    async def close(self) -> None:
        """Close the underlying client if it was created internally."""
        if self._own_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    def _prepare_headers(self, custom_headers: Dict[str, str] | None = None) -> Dict[str, str]:
        """Merge base, default, strategy, and custom headers."""
        merged = {
            "content-type": "application/json",
            **self.default_headers,
            **self.auth_strategy.get_auth_headers(),
        }
        if custom_headers:
            merged.update(custom_headers)
        return merged

    def _prepare_params(self, custom_params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Merge strategy parameters and custom parameters."""
        merged = {}
        strategy_params = self.auth_strategy.get_auth_params()
        if strategy_params:
            merged.update(strategy_params)
        if custom_params:
            # Filter None values to keep query strings clean
            merged.update({k: v for k, v in custom_params.items() if v is not None})
        return merged

    def _handle_response(self, response: httpx.Response) -> Any:
        """Convert HTTP errors to unified CRM exceptions and parse JSON content."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = response.status_code
            body = response.text
            msg = f"CRM API error {status}: {body or response.reason_phrase}"
            logger.error(msg)
            
            if status in (401, 403):
                raise CRMAuthException(msg, status_code=status, response_body=body, original_exception=e)
            elif status == 404:
                raise CRMObjectNotFoundException(msg, status_code=status, response_body=body, original_exception=e)
            elif status == 429:
                raise CRMRateLimitException(msg, status_code=status, response_body=body, original_exception=e)
            else:
                raise CRMClientException(msg, status_code=status, response_body=body, original_exception=e)

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError as e:
            raise CRMClientException(
                "Failed to parse JSON response from CRM API",
                status_code=response.status_code,
                response_body=response.text,
                original_exception=e
            )

    async def request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] | None = None,
        json: Dict[str, Any] | List[Any] | None = None,
        headers: Dict[str, str] | None = None,
        timeout: float | None = None,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> Any:
        """
        Execute an HTTP request with built-in retries and error mapping.
        
        :param method: HTTP method (GET, POST, etc.)
        :param endpoint: Relative endpoint path (will be combined with baseURL)
        :param params: Optional query parameters
        :param json: Optional JSON request payload
        :param headers: Optional request-specific headers
        :param timeout: Optional request-specific timeout override
        :param retries: Number of retry attempts for network failures
        :param backoff: Initial backoff delay in seconds
        """
        client = self._get_client()
        url = f"{self.baseURL}/{endpoint.lstrip('/')}"
        
        if self.token_manager and self.user_id and self.provider and self.db_session:
            # Fetch a valid access token, refreshing if necessary
            token = await self.token_manager.get_valid_access_token(
                session=self.db_session,
                user_id=self.user_id,
                provider=self.provider
            )
            self.auth_strategy = OAuth2BearerAuth(token)
            self.token = token
            
        merged_headers = self._prepare_headers(headers)
        merged_params = self._prepare_params(params)
        req_timeout = timeout if timeout is not None else self.timeout


        for attempt in range(retries):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    params=merged_params,
                    json=json,
                    timeout=req_timeout,
                )
                return self._handle_response(response)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(
                    f"Transient network issue (attempt {attempt + 1}/{retries}) calling {url}: {str(e)}"
                )
                if attempt == retries - 1:
                    raise CRMConnectionException(
                        f"Failed to connect to CRM API after {retries} attempts: {str(e)}",
                        original_exception=e
                    )
                await asyncio.sleep(backoff * (2**attempt))

    async def get(self, endpoint: str, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
        return await self.request("GET", endpoint, params=params, headers=headers)

    async def post(self, endpoint: str, json: Dict[str, Any] | List[Any] | None = None, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
        return await self.request("POST", endpoint, params=params, json=json, headers=headers)

    async def put(self, endpoint: str, json: Dict[str, Any] | None = None, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
        return await self.request("PUT", endpoint, params=params, json=json, headers=headers)

    async def patch(self, endpoint: str, json: Dict[str, Any] | None = None, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
        return await self.request("PATCH", endpoint, params=params, json=json, headers=headers)

    async def delete(self, endpoint: str, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Any:
        return await self.request("DELETE", endpoint, params=params, headers=headers)
