"""Repair legacy approved facts and deliver their Qdrant outbox events."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.database import SessionLocal  # noqa: E402
from app.services.knowledge.approval_consistency import (  # noqa: E402
    find_approval_inconsistencies,
    repair_approval_inconsistencies,
)
from app.services.knowledge.outbox import process_pending_events  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        result = repair_approval_inconsistencies(db)
    finally:
        db.close()

    delivered = asyncio.run(process_pending_events(limit=200))
    db = SessionLocal()
    try:
        rescanned, remaining = find_approval_inconsistencies(db)
    finally:
        db.close()
    result.update({
        "outbox_events_processed": delivered,
        "approved_drafts_rescanned": rescanned,
        "remaining_inconsistencies": len(remaining),
        "remaining": [item.to_dict() for item in remaining],
    })
    print(json.dumps(result, sort_keys=True))
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
