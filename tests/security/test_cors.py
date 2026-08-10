"""CORS contract for the supported local Vite origins."""
from fastapi.testclient import TestClient

from app.main import app


def _preflight(origin: str):
    with TestClient(app) as client:
        return client.options(
            "/api/v1/auth/google/start",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,cache-control,x-request-id,idempotency-key",
            },
        )


def test_vite_localhost_and_loopback_origins_pass_preflight():
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = _preflight(origin)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert "POST" in response.headers["access-control-allow-methods"]
        allowed_headers = response.headers["access-control-allow-headers"].lower()
        assert "content-type" in allowed_headers
        assert "cache-control" in allowed_headers
        assert "x-request-id" in allowed_headers
        assert "idempotency-key" in allowed_headers


def test_development_vite_fallback_port_passes_preflight():
    response = _preflight("http://127.0.0.1:5199")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5199"


def test_unconfigured_origin_is_not_allowed():
    response = _preflight("https://attacker.example")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
