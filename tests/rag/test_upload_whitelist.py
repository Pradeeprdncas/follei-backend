"""Step 0 regression: /upload/ must reject disallowed file types before saving."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.routers import upload as upload_module

TENANT = uuid.uuid4()
USER = uuid.uuid4()


class _FakeDB:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def _overrides(monkeypatch, tmp_path):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    monkeypatch.setattr(upload_module, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(upload_module, "ensure_topics", lambda: None)
    monkeypatch.setattr(upload_module, "get_producer", lambda: pytest.importorskip("unittest.mock").MagicMock())
    yield
    app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


def _auth_header():
    token = create_access_token(user_id=USER, tenant_id=TENANT)
    return {"Authorization": f"Bearer {token}"}


def test_exe_upload_is_rejected_before_saving(tmp_path):
    resp = client.post(
        "/upload/",
        files={"file": ("malware.exe", b"MZ\x90\x00fake-binary", "application/octet-stream")},
        data={"tenant_id": str(TENANT)},
        headers=_auth_header(),
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]
    assert list(tmp_path.iterdir()) == []


def test_winmd_upload_is_rejected(tmp_path):
    resp = client.post(
        "/upload/",
        files={"file": ("weird.winmd", b"binary-content", "application/octet-stream")},
        data={"tenant_id": str(TENANT)},
        headers=_auth_header(),
    )
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("filename", ["doc.pdf", "doc.docx", "slides.pptx", "sheet.xlsx", "data.csv", "notes.txt", "mail.eml"])
def test_whitelisted_types_pass_the_extension_check(filename, tmp_path):
    resp = client.post(
        "/upload/",
        files={"file": (filename, b"content", "application/octet-stream")},
        data={"tenant_id": str(TENANT)},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert resp.json()["filename"] == filename
    assert len(list(tmp_path.iterdir())) == 1
