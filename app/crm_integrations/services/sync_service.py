from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.crm_integrations.models.crm_connection import CRMConnection
from app.crm_integrations.models.sync_log import SyncLog
from app.crm_integrations.schemas.crm_sync import CRMSyncRequest, CRMSyncResult
from app.crm_integrations.services.crm.crm_factory import CRMFactory
from app.crm_integrations.services.token_service import TokenService


class SyncService:
    def __init__(self):
        self.token_service = TokenService()

    async def sync_provider(self, db: Session, provider: str, payload: CRMSyncRequest) -> CRMSyncResult:
        connection = db.query(CRMConnection).filter(CRMConnection.provider == provider).first()
        if not connection:
            return CRMSyncResult(provider=provider, sync_type=payload.sync_type, status="failed", records_synced=0, message="CRM connection not found.")
        log = SyncLog(provider=provider, sync_type=payload.sync_type, status="started")
        db.add(log)
        db.commit()
        db.refresh(log)
        access_token = self.token_service.decrypt_token(connection.encrypted_access_token)
        client = CRMFactory.create(provider, access_token=access_token)
        try:
            await client.test_connection()
            records_synced = 0
            if "contacts" in payload.resources:
                records_synced += len(await client.fetch_contacts())
            if "leads" in payload.resources:
                records_synced += len(await client.fetch_leads())
            log.status = "completed"
            log.records_synced = records_synced
            log.message = "Sync completed from provider API response."
        except NotImplementedError as exc:
            log.status = "failed"
            log.records_synced = 0
            log.message = str(exc)
        finally:
            log.completed_at = datetime.now(timezone.utc)
            db.commit()
        return CRMSyncResult(provider=provider, sync_type=payload.sync_type, status=log.status, records_synced=log.records_synced, message=log.message or "")
