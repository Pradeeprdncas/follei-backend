from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crm_integrations.database import get_db
from app.crm_integrations.models.sync_log import SyncLog
from app.crm_integrations.schemas.crm_sync import CRMSyncRequest, CRMSyncResult, SyncLogRead
from app.crm_integrations.security import require_api_token
from app.crm_integrations.services.sync_service import SyncService


router = APIRouter(prefix="/api/crm/sync", tags=["CRM"], dependencies=[Depends(require_api_token)])
sync_service = SyncService()


@router.post("/{provider}", response_model=CRMSyncResult)
async def sync_provider(provider: str, payload: CRMSyncRequest, db: Session = Depends(get_db)):
    return await sync_service.sync_provider(db=db, provider=provider, payload=payload)


@router.get("/logs", response_model=list[SyncLogRead])
def list_sync_logs(db: Session = Depends(get_db)):
    return db.query(SyncLog).order_by(SyncLog.started_at.desc()).limit(100).all()
