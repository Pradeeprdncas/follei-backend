"""DB session dependency for CRM integration routers/services."""
from app.database import get_db

__all__ = ["get_db"]
