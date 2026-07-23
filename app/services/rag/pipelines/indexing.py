"""End-to-end versioned indexing: parse -> classify -> chunk -> embed -> stores."""
from pathlib import Path
from sqlalchemy.orm import Session
from qdrant_client.models import PointIdsList
from app.config.database import SessionLocal
from app.config.qdrant import get_qdrant
from app.config.settings import get_settings
from app.models.chunk import Chunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.document import DocumentSection, DocumentVersion
from app.models.knowledge.entity import Entity
from app.repositories.document import DocumentRepository
from app.repositories.chunk import ChunkRepository
from app.services.rag.parsing.parser import parse_file
from app.services.rag.chunking.registry import chunk_document
from app.services.rag.classification import classify_document
from app.services.rag.document_identity import reserve_document
from app.services.rag.metadata.summarizer import summarize_text
from app.services.rag.metadata.keywords import extract_keywords
from app.services.rag.embeddings.mistral import embed_texts
from app.services.rag.embeddings.duplicate import mark_embedded
from app.services.rag.vectorstore.qdrant import ensure_collection
from app.services.rag.vectorstore.insert import insert_chunks
from app.services.knowledge.fact_extraction import extract_document_facts
from app.services.knowledge.outbox import enqueue_sync_event
from app.services.knowledge.categories import CATEGORY_CONFIGS, fact_type_for_category, normalize_category
from loguru import logger


def _prepare_failed_document_retry(db: Session, doc) -> None:
    """Remove only partial artifacts belonging to one failed document."""
    approved = db.query(BusinessFactDraft.id).filter(
        BusinessFactDraft.document_id == doc.id,
        BusinessFactDraft.approval_status == "approved",
    ).first()
    if approved:
        raise RuntimeError("A failed document with approved facts cannot be automatically reindexed")
    chunk_ids = [str(value[0]) for value in db.query(Chunk.id).filter(Chunk.document_id == doc.id).all()]
    if chunk_ids:
        get_qdrant().delete(
            collection_name=get_settings().QDRANT_COLLECTION_NAME,
            points_selector=PointIdsList(points=chunk_ids),
            wait=True,
        )
    db.query(BusinessFactDraft).filter(BusinessFactDraft.document_id == doc.id).delete(synchronize_session=False)
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete(synchronize_session=False)
    doc.status = "processing"
    doc.metadata_ = {**(doc.metadata_ or {}), "retrying_failed_document": True}
    db.commit()


def enqueue_document_memory_projection(db: Session, *, doc, chunk_count: int) -> None:
    """Idempotently schedule the clean FerretDB projection for an indexed document."""
    sections = db.query(DocumentSection).filter(DocumentSection.document_id == doc.id, DocumentSection.tenant_id == doc.tenant_id).order_by(DocumentSection.section_order).all()
    entities = db.query(Entity).filter(Entity.document_id == doc.id, Entity.tenant_id == doc.tenant_id).all()
    enqueue_sync_event(
        db,
        tenant_id=doc.tenant_id,
        event_type="document.indexed",
        aggregate_type="document",
        aggregate_id=doc.id,
        payload={
            "title": doc.title,
            "source_type": doc.source_type,
            "category": doc.category,
            "primary_category": doc.primary_category or doc.category,
            "secondary_categories": list(doc.secondary_categories or []),
            "workspace_id": str(doc.workspace_id) if doc.workspace_id else None,
            "version": doc.version,
            "document_version_id": str(db.query(DocumentVersion.id).filter(DocumentVersion.document_id == doc.id, DocumentVersion.version == doc.version).scalar() or ""),
            "summary": doc.summary or "",
            "keywords": list(doc.keywords or []),
            "chunk_count": int(chunk_count),
            "source_uri": doc.source_uri,
            "source_metadata": dict(doc.metadata_ or {}),
            "previous_document_id": str(doc.previous_document_id) if doc.previous_document_id else None,
            "sections": [{"section_id": str(row.id), "order": row.section_order, "title": row.title, "category": row.category, "section_type": row.section_type, "summary": row.summary, "source_chunk_ids": [str(chunk.id) for chunk in row.chunks]} for row in sections],
            "entities": [{"entity_id": str(row.id), "entity_type": row.entity_type, "entity_name": row.name, "category": row.category, "schema_key": row.schema_key, "schema_version": row.schema_version, "status": row.status, "data": row.data or {}, "source": {"chunk_ids": [str((row.metadata_ or {}).get("source_chunk_id"))] if (row.metadata_ or {}).get("source_chunk_id") else []}, "confidence": float(row.confidence) if row.confidence is not None else None} for row in entities],
        },
        idempotency_key=f"document.indexed:{doc.id}:v{doc.version}",
    )


async def index_document(file_path: str, tenant_id: str, *, source_uri: str | None = None, original_filename: str | None = None, uploaded_by: str | None = None, category_override: str | None = None, workspace_id: str | None = None, processing_instructions: str | None = None, source_metadata: dict | None = None, return_details: bool = False, db: Session | None = None) -> str | dict:
    """Index one source idempotently; identical content is never re-embedded."""
    path = Path(file_path)
    close_db = db is None
    db = db or SessionLocal()
    doc_repo = DocumentRepository(db)
    try:
        filename = original_filename or path.name
        source_type = path.suffix.lower().lstrip(".")
        source_uri = source_uri or f"file://{path.resolve()}"
        doc, duplicate = reserve_document(db=db, tenant_id=tenant_id, file_path=path, source_uri=source_uri, filename=filename, source_type=source_type, uploaded_by=uploaded_by, workspace_id=workspace_id, processing_instructions=processing_instructions, source_metadata=source_metadata)
        if duplicate and doc.status != "failed":
            if source_metadata:
                existing_chunk_ids = [str(value[0]) for value in db.query(Chunk.id).filter(Chunk.document_id == doc.id, Chunk.tenant_id == tenant_id).all()]
                if existing_chunk_ids:
                    get_qdrant().set_payload(
                        collection_name=get_settings().QDRANT_COLLECTION_NAME,
                        points=existing_chunk_ids,
                        payload={
                            "lead_ids": list((doc.metadata_ or {}).get("lead_ids") or []),
                            "lead_import_job_ids": list((doc.metadata_ or {}).get("lead_import_job_ids") or []),
                            "lead_import_row_ids": list((doc.metadata_ or {}).get("lead_import_row_ids") or []),
                        },
                    )
            enqueue_document_memory_projection(
                db,
                doc=doc,
                chunk_count=db.query(Chunk.id).filter(Chunk.document_id == doc.id, Chunk.tenant_id == tenant_id).count(),
            )
            db.commit()
            logger.info(f"Skipping duplicate document {doc.id}; hash already indexed")
            details = {"document_id": str(doc.id), "disposition": "duplicate", "version": doc.version, "status": doc.status}
            return details if return_details else str(doc.id)
        if duplicate:
            _prepare_failed_document_retry(db, doc)
            logger.info(f"Retrying failed document {doc.id} after cleaning partial artifacts")

        pages = parse_file(path)
        classified_category = await classify_document(filename=filename, pages=pages, source_type=source_type)
        try:
            category = normalize_category(category_override or classified_category)
        except ValueError:
            category = "general"
        doc.category = category
        doc.primary_category = category
        doc.extractor_version = "category-registry-v1"
        doc.chunker_version = f"{CATEGORY_CONFIGS[category]['chunking_hint']}-v1"
        doc.total_pages = len(pages)
        db.commit()
        chunks_data = chunk_document(path, pages, metadata={"source_type": source_type, "category": category, "sensitivity": doc.sensitivity})
        all_text = " ".join(chunk["text"] for chunk in chunks_data)
        keywords = extract_keywords(all_text, top_n=10)
        summary = await summarize_text(all_text[:10000])

        version_row = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.version.desc()).first()
        sections: dict[tuple[str, int], DocumentSection] = {}
        for chunk_data in chunks_data:
            page = int(chunk_data.get("page") or 0)
            key = (str(chunk_data.get("heading") or "Document content"), page)
            if key not in sections:
                section = DocumentSection(tenant_id=tenant_id, document_id=doc.id, document_version_id=version_row.id if version_row else None, section_order=len(sections), title=key[0], category=category, section_type=CATEGORY_CONFIGS[category]["chunking_hint"], page_start=page or None, page_end=page or None, content="", metadata_={"user_selected_primary_category": category})
                db.add(section); db.flush(); sections[key] = section
            sections[key].content = (sections[key].content or "") + "\n" + str(chunk_data["text"])

        chunk_records: list[Chunk] = []
        for index, chunk_data in enumerate(chunks_data):
            page = int(chunk_data.get("page") or 0)
            section = sections[(str(chunk_data.get("heading") or "Document content"), page)]
            chunk_records.append(Chunk(
                id=chunk_data["chunk_id"], document_id=doc.id, tenant_id=tenant_id, document_version_id=version_row.id if version_row else None, section_id=section.id, primary_category=category, detected_category=category, chunk_index=index,
                text=chunk_data["text"], page=chunk_data.get("page", 0), heading=chunk_data.get("heading"),
                parent_chunk_id=chunk_data.get("parent_chunk_id"), prev_chunk_id=chunk_data.get("prev_chunk_id"),
                next_chunk_id=chunk_data.get("next_chunk_id"), chunk_type=chunk_data.get("chunk_type"),
                section_path=chunk_data.get("section_path"), word_count=chunk_data.get("word_count"),
                tags=keywords[:5] + [f"category:{category}", "approval:draft"], permissions=[],
            ))

        if chunk_records:
            ChunkRepository(db).create_many(chunk_records)
            embeddings = await embed_texts([chunk.text for chunk in chunk_records])
            payloads = []
            for chunk in chunk_records:
                chunk.embedding_hash = mark_embedded(chunk.text, str(chunk.id))
                payloads.append({
                    "text": chunk.text, "chunk_id": str(chunk.id), "document_id": str(chunk.document_id),
                    "tenant_id": str(chunk.tenant_id), "page": chunk.page, "heading": chunk.heading,
                    "chunk_type": chunk.chunk_type, "parent_chunk_id": chunk.parent_chunk_id,
                    "prev_chunk_id": chunk.prev_chunk_id, "next_chunk_id": chunk.next_chunk_id,
                    "section_path": chunk.section_path, "heading_path": chunk.section_path or [],
                    "word_count": chunk.word_count, "tags": chunk.tags, "category": category, "primary_category": category, "detected_category": chunk.detected_category, "section_id": str(chunk.section_id) if chunk.section_id else None, "document_version_id": str(chunk.document_version_id) if chunk.document_version_id else None,
                    "approval_status": "draft", "sensitivity": doc.sensitivity, "source_type": source_type,
                    "lead_ids": list((doc.metadata_ or {}).get("lead_ids") or []),
                    "lead_import_job_ids": list((doc.metadata_ or {}).get("lead_import_job_ids") or []),
                    "lead_import_row_ids": list((doc.metadata_ or {}).get("lead_import_row_ids") or []),
                })
            ensure_collection()
            insert_chunks([str(chunk.id) for chunk in chunk_records], embeddings, payloads)
            db.commit()

        doc_repo.update_summary(str(doc.id), summary, keywords, len(chunk_records))
        drafts = await extract_document_facts(db, document=doc, chunks=chunk_records)
        # A flexible draft entity preserves every extracted field without
        # publishing it into an operational product/policy table prematurely.
        for draft in drafts:
            payload = dict(draft.payload or {})
            name = str(payload.get("name") or payload.get("title") or payload.get("question") or doc.title)
            db.add(Entity(tenant_id=doc.tenant_id, workspace_id=doc.workspace_id, document_id=doc.id, document_version_id=version_row.id if version_row else None, entity_type=draft.fact_type, name=name, category=category, schema_key=f"{category}:{draft.fact_type}", schema_version="1", data=payload, confidence=draft.extraction_confidence, status="draft", metadata_={"fact_id": str(draft.id), "source_chunk_id": str(draft.chunk_id) if draft.chunk_id else None}))
        enqueue_document_memory_projection(db, doc=doc, chunk_count=len(chunk_records))
        db.commit()
        logger.info(f"Indexed document={doc.id} version={doc.version} category={category} chunks={len(chunk_records)}")
        details = {"document_id": str(doc.id), "disposition": "new_version" if doc.previous_document_id else "new", "version": doc.version, "status": doc.status}
        return details if return_details else str(doc.id)
    except Exception:
        if "doc" in locals():
            doc_repo.update_status(str(doc.id), "failed")
        raise
    finally:
        if close_db:
            db.close()

