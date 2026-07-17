"""MCP custom exception hierarchy."""


class MCPException(Exception):
    """Base exception for all MCP related failures."""
    pass


class ToolNotFoundError(MCPException):
    """Raised when the requested tool does not exist in the registry."""
    pass


class PermissionDeniedError(MCPException):
    """Raised when the context credentials do not allow executing the tool."""
    pass


class RateLimitExceededError(MCPException):
    """Raised when execution is throttled."""
    pass


class ConnectorError(MCPException):
    """Base exception for external integration connector errors."""
    pass


class AuthError(ConnectorError):
    """Raised when authentication with external connector fails/expires."""
    pass


class ExecutionError(MCPException):
    """Raised when the backend API execution fails."""
    pass


class ValidationError(MCPException):
    """Raised when parameters fail to conform to the input schema."""
    pass
