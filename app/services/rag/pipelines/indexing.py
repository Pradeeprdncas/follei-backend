"""End-to-end versioned indexing: parse -> classify -> chunk -> embed -> stores."""
from pathlib import Path
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.models.chunk import Chunk
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
from loguru import logger


async def index_document(file_path: str, tenant_id: str, *, source_uri: str | None = None, original_filename: str | None = None, uploaded_by: str | None = None, db: Session | None = None) -> str:
    """Index one source idempotently; identical content is never re-embedded."""
    path = Path(file_path)
    close_db = db is None
    db = db or SessionLocal()
    doc_repo = DocumentRepository(db)
    try:
        filename = original_filename or path.name
        source_type = path.suffix.lower().lstrip(".")
        source_uri = source_uri or f"file://{path.resolve()}"
        doc, duplicate = reserve_document(db=db, tenant_id=tenant_id, file_path=path, source_uri=source_uri, filename=filename, source_type=source_type, uploaded_by=uploaded_by)
        if duplicate:
            logger.info(f"Skipping duplicate document {doc.id}; hash already indexed")
            return str(doc.id)

        pages = parse_file(path)
        category = await classify_document(filename=filename, pages=pages, source_type=source_type)
        doc.category = category
        doc.total_pages = len(pages)
        db.commit()
        chunks_data = chunk_document(path, pages, metadata={"source_type": source_type, "category": category, "sensitivity": doc.sensitivity})
        all_text = " ".join(chunk["text"] for chunk in chunks_data)
        keywords = extract_keywords(all_text, top_n=10)
        summary = await summarize_text(all_text[:10000])

        chunk_records: list[Chunk] = []
        for index, chunk_data in enumerate(chunks_data):
            chunk_records.append(Chunk(
                id=chunk_data["chunk_id"], document_id=doc.id, tenant_id=tenant_id, chunk_index=index,
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
                    "word_count": chunk.word_count, "tags": chunk.tags, "category": category,
                    "approval_status": "draft", "sensitivity": doc.sensitivity, "source_type": source_type,
                })
            ensure_collection()
            insert_chunks([str(chunk.id) for chunk in chunk_records], embeddings, payloads)
            db.commit()

        doc_repo.update_summary(str(doc.id), summary, keywords, len(chunk_records))
        await extract_document_facts(db, document=doc, chunks=chunk_records)
        logger.info(f"Indexed document={doc.id} version={doc.version} category={category} chunks={len(chunk_records)}")
        return str(doc.id)
    except Exception:
        if "doc" in locals():
            doc_repo.update_status(str(doc.id), "failed")
        raise
    finally:
        if close_db:
            db.close()

