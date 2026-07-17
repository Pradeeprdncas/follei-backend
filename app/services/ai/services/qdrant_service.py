"""Qdrant Service - Production vector database health checker with graceful degradation."""
from typing import Dict, Any
from loguru import logger


class QdrantService:
    """Production Qdrant service with graceful skip.

    - connect(): Establish connection
    - ping(): Test connectivity
    - health(): Return health status
    Never crashes startup.
    """

    def __init__(self):
        self._client = None
        self._enabled = True
        self._configured = False
        self._init()

    def _init(self):
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            qdrant_url = getattr(settings, 'QDRANT_URL', None) or \
                         getattr(settings, 'QDRANT_HOST', None)
            self._enabled = qdrant_url is not None
            self._configured = True
        except Exception:
            self._enabled = False
            self._configured = False

    def connect(self):
        """Establish Qdrant connection."""
        if not self._enabled:
            return False
        try:
            from qdrant_client import QdrantClient
            from app.config.settings import get_settings
            settings = get_settings()
            qdrant_url = getattr(settings, 'QDRANT_URL', None)
            qdrant_host = getattr(settings, 'QDRANT_HOST', None)
            qdrant_port = getattr(settings, 'QDRANT_PORT', 6333)
            if qdrant_url:
                self._client = QdrantClient(url=qdrant_url)
            elif qdrant_host:
                self._client = QdrantClient(host=qdrant_host, port=qdrant_port)
            return self._client is not None
        except ImportError:
            logger.warning("qdrant-client not installed")
            self._enabled = False
            return False
        except Exception:
            self._enabled = False
            return False

    def ping(self) -> bool:
        """Test Qdrant connectivity."""
        if not self._enabled or not self._client:
            return False
        try:
            import asyncio
            collections = asyncio.run(self._client.get_collections())
            return collections is not None
        except Exception:
            return False

    def health(self) -> Dict[str, Any]:
        """Get Qdrant health status."""
        try:
            if self.ping():
                return {"qdrant": "healthy", "status": "ok"}
        except Exception:
            pass
        if not self._enabled:
            return {"qdrant": "disabled", "status": "skipped"}
        return {"qdrant": "unreachable", "status": "degraded"}


# Singleton
_qdrant_service: QdrantService = None


def get_qdrant_service() -> QdrantService:
    """Get or create singleton Qdrant service."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service