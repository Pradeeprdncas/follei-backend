from fastapi.testclient import TestClient

from app.main import app


def test_swagger_uses_local_assets_and_exposes_full_schema():
    client = TestClient(app)
    docs = client.get("/docs")
    javascript = client.get("/api-docs-assets/swagger-ui-bundle.js")
    stylesheet = client.get("/api-docs-assets/swagger-ui.css")
    schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert javascript.status_code == 200
    assert stylesheet.status_code == 200
    assert schema.status_code == 200
    assert schema.json()["openapi"] == "3.0.3"
    assert "/api-docs-assets/swagger-ui-bundle.js" in docs.text
    assert "/api-docs-assets/swagger-ui.css" in docs.text
    assert len(schema.json()["paths"]) >= 200
