"""OpenAPI classification for mounted product and scaffolding APIs.

This module changes documentation metadata only.  It deliberately does not
unmount routes: callers can still use future/unstable domains while Swagger
makes their support level unambiguous.
"""

from fastapi import FastAPI
from fastapi.routing import APIRoute


FUTURE_UNSTABLE_TAG = "Future / unstable"

_FUTURE_DOMAIN_TAGS = {
    "Domain 3 - Agents & AI Workforce",
    "CRM Sync",
    "Campaigns",
    "Customers & Customer Success",
    "Tools, MCP & Registry",
}
_FUTURE_PATH_PREFIXES = (
    "/api/opportunities",
    "/api/meetings",
)


def classify_mounted_api_surface(app: FastAPI) -> None:
    """Add a visible support-level tag to mounted scaffolding domains."""
    # FastAPI 0.128+ keeps included routers as lazy ``_IncludedRouter``
    # wrappers.  Mutate their source APIRoutes so both runtime resolution and
    # later OpenAPI generation see the classification.
    for mounted in app.routes:
        source_router = getattr(mounted, "original_router", None)
        routes = source_router.routes if source_router is not None else (mounted,)
        prefix = getattr(getattr(mounted, "include_context", None), "prefix", "")
        for route in routes:
            if not isinstance(route, APIRoute):
                continue
            full_path = f"{prefix}{route.path}"
            is_future_domain = bool(set(route.tags) & _FUTURE_DOMAIN_TAGS)
            is_future_path = full_path.startswith(_FUTURE_PATH_PREFIXES)
            if (is_future_domain or is_future_path) and FUTURE_UNSTABLE_TAG not in route.tags:
                route.tags.insert(0, FUTURE_UNSTABLE_TAG)
