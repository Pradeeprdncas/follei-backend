from sqlalchemy.orm import Session
from app.crm_integrations.models.sync_log import SyncLog


def list_failed_syncs(db: Session, limit: int = 50):
    return db.query(SyncLog).filter(SyncLog.status == "failed").order_by(SyncLog.started_at.desc()).limit(limit).all()
