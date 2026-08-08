"""Live tenant-policy resolution against active channel connections."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.database import SessionLocal
from app.core.security import create_access_token
from app.domains.lead_import.validators import evaluate_lead_batch, resolve_lead_import_policy
from app.main import app
from app.models.integrations.channel_connection import TenantChannelConnection
from app.models.tenancy import Tenant


client = TestClient(app)


@pytest.mark.integration
def test_email_only_tenant_passes_email_but_redundancy_tenant_rejects_same_row():
    email_tenant_id = uuid4()
    whatsapp_tenant_id = uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=email_tenant_id, name="Email Only", slug=f"email-{email_tenant_id.hex[:8]}", lead_contact_requirement=1),
            Tenant(id=whatsapp_tenant_id, name="WhatsApp Redundancy", slug=f"wa-{whatsapp_tenant_id.hex[:8]}", lead_contact_requirement=2),
        ])
        db.flush()
        db.add_all([
            TenantChannelConnection(
                tenant_id=whatsapp_tenant_id,
                channel="whatsapp",
                provider="meta",
                identity="+15550000001",
                enabled=True,
                verified=True,
                status="active",
            ),
            TenantChannelConnection(
                tenant_id=email_tenant_id,
                channel="voice",
                provider="twilio",
                identity="+15550000009",
                enabled=True,
                verified=False,
                status="verification_failed",
            ),
        ])
        db.commit()

        email_policy = resolve_lead_import_policy(db, email_tenant_id)
        whatsapp_policy = resolve_lead_import_policy(db, whatsapp_tenant_id)
        lead = {"email": "reachable@example.com"}

        email_batch = evaluate_lead_batch([lead], policy=email_policy)
        whatsapp_batch = evaluate_lead_batch([lead], policy=whatsapp_policy)

        assert email_policy["minimum_contact_methods"] == 1
        assert email_policy["accepted_contact_methods"] == ["email"]
        assert email_batch["accepted_rows"] == 1
        assert whatsapp_policy["minimum_contact_methods"] == 2
        assert whatsapp_policy["accepted_contact_methods"] == ["email", "whatsapp"]
        assert whatsapp_batch["accepted_rows"] == 0
        assert whatsapp_batch["rejected_rows"] == 1

        db.query(TenantChannelConnection).filter_by(tenant_id=whatsapp_tenant_id).delete()
        db.query(Tenant).filter(Tenant.id.in_([email_tenant_id, whatsapp_tenant_id])).delete(synchronize_session=False)
        db.commit()


@pytest.mark.integration
def test_preview_response_exposes_each_tenants_resolved_policy():
    email_tenant_id = uuid4()
    whatsapp_tenant_id = uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=email_tenant_id, name="Preview Email", slug=f"preview-email-{email_tenant_id.hex[:8]}", lead_contact_requirement=1),
            Tenant(id=whatsapp_tenant_id, name="Preview WhatsApp", slug=f"preview-wa-{whatsapp_tenant_id.hex[:8]}", lead_contact_requirement=2),
        ])
        db.flush()
        db.add(TenantChannelConnection(
            tenant_id=whatsapp_tenant_id,
            channel="whatsapp",
            provider="meta",
            identity="+15550000002",
            enabled=True,
            verified=True,
            status="active",
        ))
        db.commit()

    csv_file = {"file": ("leads.csv", b"email\nreachable@example.com\n", "text/csv")}
    email_response = client.post(
        "/api/leads/import/preview",
        headers={"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=email_tenant_id)}"},
        files=csv_file,
    )
    whatsapp_response = client.post(
        "/api/leads/import/preview",
        headers={"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=whatsapp_tenant_id)}"},
        files=csv_file,
    )

    assert email_response.status_code == 200
    assert email_response.json()["valid_rows"] == 1
    assert email_response.json()["policy"]["minimum_contact_methods"] == 1
    assert email_response.json()["policy"]["accepted_contact_methods"] == ["email"]
    assert whatsapp_response.status_code == 200
    assert whatsapp_response.json()["valid_rows"] == 0
    assert whatsapp_response.json()["policy"]["minimum_contact_methods"] == 2
    assert whatsapp_response.json()["policy"]["accepted_contact_methods"] == ["email", "whatsapp"]

    with SessionLocal() as db:
        db.query(TenantChannelConnection).filter_by(tenant_id=whatsapp_tenant_id).delete()
        db.query(Tenant).filter(Tenant.id.in_([email_tenant_id, whatsapp_tenant_id])).delete(synchronize_session=False)
        db.commit()
