"""Backfill clean FerretDB memory projections for already indexed documents."""
from __future__ import annotations

import asyncio
import json

from app.config.database import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.knowledge.outbox import process_pending_events
from app.services.rag.pipelines.indexing import enqueue_document_memory_projection


async def main() -> None:
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(Document.status.in_(("indexed", "ready"))).all()
        for document in documents:
            chunk_count = db.query(Chunk.id).filter(
                Chunk.document_id == document.id,
                Chunk.tenant_id == document.tenant_id,
            ).count()
            enqueue_document_memory_projection(db, doc=document, chunk_count=chunk_count)
        db.commit()
        scanned = len(documents)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    processed = await process_pending_events(limit=max(25, scanned + 10))
    print(json.dumps({"indexed_documents_scanned": scanned, "sync_events_processed": processed}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
