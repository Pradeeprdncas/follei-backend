"""JSON-RPC 2.0 parsing and validation models for MCP."""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class JSONRPCError(BaseModel):
    """Standard JSON-RPC 2.0 Error model."""
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCRequest(BaseModel):
    """Standard JSON-RPC 2.0 Request model."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Union[Dict[str, Any], List[Any], None]] = None
    id: Union[int, str]

    @field_validator("jsonrpc")
    @classmethod
    def validate_jsonrpc(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError("jsonrpc version must be '2.0'")
        return v


class JSONRPCResponse(BaseModel):
    """Standard JSON-RPC 2.0 Response model."""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
    id: Optional[Union[int, str]] = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_jsonrpc(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError("jsonrpc version must be '2.0'")
        return v


class JSONRPCNotification(BaseModel):
    """Standard JSON-RPC 2.0 Notification model."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Union[Dict[str, Any], List[Any], None]] = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_jsonrpc(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError("jsonrpc version must be '2.0'")
        return v


# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def make_error_response(
    code: int, message: str, id_val: Optional[Union[int, str]] = None, data: Optional[Any] = None
) -> Dict[str, Any]:
    """Generates standard JSON-RPC error response dict."""
    return {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message,
            **({"data": data} if data is not None else {})
        },
        "id": id_val
    }


def make_success_response(result: Any, id_val: Union[int, str]) -> Dict[str, Any]:
    """Generates standard JSON-RPC success response dict."""
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": id_val
    }
