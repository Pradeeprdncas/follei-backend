"""PostgreSQL regression coverage for Workspace source/connection ordering."""
from uuid import uuid4

from app.config.database import SessionLocal
from app.models.tenancy import Tenant
from app.services.integrations.google_workspace import GoogleWorkspaceOAuthService


def test_workspace_source_exists_before_connection_foreign_key_is_inserted():
    tenant_id = uuid4()
    subject = f"google-persistence-{uuid4().hex}"

    with SessionLocal() as db:
        db.add(Tenant(
            id=tenant_id,
            name="Google persistence test",
            slug=f"google-persistence-{uuid4().hex[:10]}",
            status="active",
            is_active=True,
            timezone="Asia/Kolkata",
            lead_contact_requirement=1,
        ))
        db.commit()

        try:
            connection, run, jobs = GoogleWorkspaceOAuthService().persist_workspace_connection(
                db,
                tenant_id=tenant_id,
                token_data={
                    "access_token": "test-access-token",
                    "refresh_token": "test-refresh-token",
                    "expires_in": 3600,
                    "scope": "openid email",
                },
                identity={
                    "sub": subject,
                    "email": f"{subject}@example.com",
                },
                resources=["gmail", "drive", "calendar", "contacts"],
            )

            assert connection.source_id is not None
            assert run.source_id == connection.source_id
            assert len(jobs) == 4
            assert {job.payload["resource"] for job in jobs} == {
                "gmail",
                "drive",
                "calendar",
                "contacts",
            }
        finally:
            tenant = db.get(Tenant, tenant_id)
            if tenant:
                db.delete(tenant)
                db.commit()
