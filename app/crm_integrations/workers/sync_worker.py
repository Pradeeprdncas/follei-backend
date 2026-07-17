from sqlalchemy.orm import Session
from app.crm_integrations.models.crm_connection import CRMConnection
from app.crm_integrations.schemas.crm_sync import CRMSyncRequest
from app.crm_integrations.services.sync_service import SyncService


async def run_auto_sync(db: Session):
    sync_service = SyncService()
    connections = db.query(CRMConnection).filter(CRMConnection.auto_sync.is_(True)).all()
    for connection in connections:
        payload = CRMSyncRequest(provider=connection.provider, sync_type="scheduled")
        await sync_service.sync_provider(db=db, provider=connection.provider, payload=payload)
