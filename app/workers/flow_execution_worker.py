"""Dedicated, idempotent lead nurturing flow worker."""
import os
import time
from loguru import logger

from app.database.session import SessionLocal
from app.services.flows.service import process_due, reconcile_active_flows


def run() -> None:
    interval = max(1.0, float(os.getenv("FLOW_WORKER_POLL_SECONDS", "3")))
    reconcile_interval = max(10.0, float(os.getenv("FLOW_RECONCILE_SECONDS", "30")))
    last_reconcile = 0.0
    logger.info("Flow execution worker started (poll={}s)", interval)
    while True:
        with SessionLocal() as db:
            try:
                now = time.monotonic()
                if now - last_reconcile >= reconcile_interval:
                    result = reconcile_active_flows(db)
                    last_reconcile = now
                    if result["enrolled"]:
                        logger.info("Reconciled {} missing lead enrollment(s)", result["enrolled"])
                processed = process_due(db)
                if processed: logger.info("Processed {} flow steps", processed)
            except Exception:
                db.rollback()
                logger.exception("Flow execution cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    run()
