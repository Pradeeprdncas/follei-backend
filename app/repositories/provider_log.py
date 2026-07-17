"""ProviderLogRepository — observability logs for every provider call."""
from uuid import UUID
from typing import Any
from app.repositories.base import BaseRepository
from app.models.campaigns import ProviderLog


class ProviderLogRepository(BaseRepository[ProviderLog]):
    def __init__(self, db):
        super().__init__(db, ProviderLog)

    def _uuid(self, value: Any) -> UUID:
        if isinstance(value, str):
            return UUID(value)
        return value

    def create(self, log: ProviderLog) -> ProviderLog:
        self.db.add(log)
        self.db.commit()
        return log
