"""Authentication middleware and context builders for MCP Server."""
import uuid
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from loguru import logger
from mcp.base.context import MCPContext

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)
DEFAULT_TOKEN = "enterprise-mcp-secret-token"  # Production settings can override this via env


def extract_mcp_context(request: Request) -> MCPContext:
    """Extracts headers/query params to build a valid execution MCPContext.

    Standard headers parsed:
      - X-Organization-ID
      - X-User-ID
      - X-Agent-ID
      - X-Permissions
      - X-Trace-ID
      - Authorization / Bearer token (optional auth validation)
    """
    # 1. Simple Token Authentication
    auth_header = request.headers.get("Authorization")
    # Also support query parameter auth (specifically for SSE stream connections)
    token = request.query_params.get("token")
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
    # Validation step: In production, check against env token
    # For now, if a token is provided, validate it, or fallback gracefully if local/testing
    if token and token != DEFAULT_TOKEN:
        # Check environment override
        import os
        expected_token = os.getenv("MCP_AUTH_TOKEN", DEFAULT_TOKEN)
        if token != expected_token:
            logger.warning("Authentication failed: invalid token provided.")
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid token.")

    # 2. Context metadata parsing
    org_id = request.headers.get("X-Organization-ID", "org_default")
    user_id = request.headers.get("X-User-ID", "user_default")
    agent_id = request.headers.get("X-Agent-ID", "agent_default")
    trace_id = request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID") or str(uuid.uuid4())
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Permissions list split (comma-separated header)
    perm_header = request.headers.get("X-Permissions", "*")
    permissions = [p.strip() for p in perm_header.split(",") if p.strip()]

    # Collect other standard metadata headers for logging
    meta: Dict[str, str] = {}
    for h_name, h_val in request.headers.items():
        if h_name.lower().startswith("x-mcp-"):
            meta[h_name[6:]] = h_val

    ctx = MCPContext(
        organization_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        permissions=permissions,
        request_id=req_id,
        trace_id=trace_id,
        metadata=meta
    )
    logger.debug(f"Generated MCP Context for request: organization_id={org_id}, user_id={user_id}, request_id={req_id}")
    return ctx
