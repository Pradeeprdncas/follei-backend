"""Frontend-stable response envelope for asynchronous onboarding APIs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def api_envelope(data: Any, *, errors: list[dict[str, Any]] | None = None, **meta: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "request_id": str(uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **meta,
        },
        "errors": errors or [],
    }
