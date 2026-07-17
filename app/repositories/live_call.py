"""LiveCall repository."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.live_call import LiveCallTranscription, CallTranscriptionChunk


class LiveCallRepository(BaseRepository[LiveCallTranscription]):
    def __init__(self, db: Session):
        super().__init__(db, LiveCallTranscription)

    def get_by_tenant(self, tenant_id: Any) -> list[LiveCallTranscription]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(LiveCallTranscription).filter(
            LiveCallTranscription.tenant_id == tid
        ).order_by(LiveCallTranscription.created_at.desc()).all()

    def get_active_calls(self, tenant_id: Any) -> list[LiveCallTranscription]:
        tid = self._to_uuid(tenant_id)
        return self.db.query(LiveCallTranscription).filter(
            LiveCallTranscription.tenant_id == tid,
            LiveCallTranscription.status == "active",
        ).all()


class CallChunkRepository(BaseRepository[CallTranscriptionChunk]):
    def __init__(self, db: Session):
        super().__init__(db, CallTranscriptionChunk)

    def get_by_live_call(self, live_call_id: Any) -> list[CallTranscriptionChunk]:
        lid = self._to_uuid(live_call_id)
        return self.db.query(CallTranscriptionChunk).filter(
            CallTranscriptionChunk.live_call_id == lid
        ).order_by(CallTranscriptionChunk.start_timestamp).all()
