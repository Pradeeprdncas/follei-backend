"""OpenAPI contract checks for canonical, legacy, and scaffolding APIs."""

from app.api_surface import FUTURE_UNSTABLE_TAG
from app.main import app


def _operation(schema: dict, path: str, method: str) -> dict:
    return schema["paths"][path][method.lower()]


def test_onboarding_and_lead_import_support_levels_are_explicit() -> None:
    schema = app.openapi()

    for path, method in (
        ("/api/v1/onboarding/status", "get"),
        ("/api/v1/onboarding/extractions", "get"),
        ("/api/v1/onboarding/extractions/{draft_id}", "patch"),
        ("/api/leads/import", "post"),
        ("/api/leads/import/async", "post"),
    ):
        operation = _operation(schema, path, method)
        assert operation["deprecated"] is True
        assert "Legacy / compatibility" in operation["tags"]

    for path, method in (
        ("/api/v1/onboarding/profile", "post"),
        ("/api/v1/onboarding/complete", "post"),
        ("/api/v1/onboarding/state", "get"),
        ("/api/v1/onboarding/categories/{key}/items", "get"),
        ("/api/leads/import/upload", "post"),
        ("/api/leads/import/{job_id}/commit", "post"),
    ):
        operation = _operation(schema, path, method)
        assert operation.get("deprecated", False) is False


def test_scaffolding_domains_are_visibly_future_unstable() -> None:
    schema = app.openapi()
    domain_tags = {
        "Domain 3 - Agents & AI Workforce",
        "CRM Sync",
        "Campaigns",
        "Customers & Customer Success",
        "Tools, MCP & Registry",
    }
    classified = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            is_named_domain = bool(set(operation.get("tags", [])) & domain_tags)
            is_revenue_scaffold = path.startswith(("/api/opportunities", "/api/meetings"))
            if is_named_domain or is_revenue_scaffold:
                classified.append((method, path))
                assert FUTURE_UNSTABLE_TAG in operation["tags"], (method, path)

    assert classified, "Expected at least one mounted future/unstable operation"
