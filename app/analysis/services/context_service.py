from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import get_settings

_settings = get_settings()

logger = logging.getLogger(__name__)


class LeadContextService:
    """Loads CRM and business context without requiring it in every request."""

    @staticmethod
    def _from_json(path_value: str, session_id: str) -> dict[str, Any]:
        if not path_value:
            return {}
        path = Path(path_value)
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                value = payload.get(session_id, payload.get("default", payload))
                return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load lead context from %s: %s", path, exc)
        return {}

    @classmethod
    async def crm_context(cls, session_id: str) -> dict[str, Any]:
        local = cls._from_json(_settings.CRM_CONTEXT_PATH, session_id)
        if not _settings.CRM_API_URL:
            return local
        headers = {"Authorization": f"Bearer {_settings.CRM_API_TOKEN}"} if _settings.CRM_API_TOKEN else {}
        try:
            async with httpx.AsyncClient(timeout=_settings.CONTEXT_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _settings.CRM_API_URL.rstrip("/") + f"/leads/{session_id}", headers=headers
                )
                response.raise_for_status()
                remote = response.json()
                if isinstance(remote, dict):
                    return {**local, **remote}
        except Exception as exc:
            logger.warning("CRM lookup failed for %s: %s", session_id, exc)
        return local

    @classmethod
    async def business_docs(cls, session_id: str) -> list[str]:
        context = cls._from_json(_settings.BUSINESS_CONTEXT_PATH, session_id)
        docs = context.get("documents", context.get("business_docs", []))
        return [str(item) for item in docs] if isinstance(docs, list) else []

    @classmethod
    async def resolve(cls, session_id: str) -> tuple[dict[str, Any], list[str]]:
        crm, docs = await __import__("asyncio").gather(
            cls.crm_context(session_id), cls.business_docs(session_id)
        )
        return crm, docs
