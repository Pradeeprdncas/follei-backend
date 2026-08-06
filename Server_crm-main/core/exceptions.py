"""
Core Exceptions for CRM Gateway.
Defines a robust error taxonomy to isolate the application logic from raw HTTP/network errors.
"""

class CRMGatewayException(Exception):
    """Base exception for all CRM Gateway errors."""
    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.original_exception = original_exception


class CRMClientException(CRMGatewayException):
    """Exception raised for HTTP client failures (4xx/5xx responses)."""
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None, original_exception: Exception | None = None):
        super().__init__(message, original_exception)
        self.status_code = status_code
        self.response_body = response_body


class CRMAuthException(CRMClientException):
    """Exception raised for authentication or authorization failures (401/403 status)."""
    pass


class CRMConnectionException(CRMGatewayException):
    """Exception raised for connection timeouts, DNS resolution failures, etc."""
    pass


class CRMRateLimitException(CRMClientException):
    """Exception raised when a CRM provider rate-limits API requests (429 status)."""
    pass


class CRMObjectNotFoundException(CRMClientException):
    """Exception raised when a requested CRM resource (contact, company, deal) is not found (404 status)."""
    pass


class CRMAdapterNotFoundException(CRMGatewayException):
    """Exception raised when a requested CRM provider is not registered in the AdapterFactory."""
    pass


class CRMValidationException(CRMGatewayException):
    """Exception raised when local data validation fails or mapping cannot be performed."""
    pass
