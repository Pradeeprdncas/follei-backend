"""End-to-end indexing pipeline: file → chunks → embeddings → Qdrant + PostgreSQL."""
from pathlib import Path
import uuid
from sqlalchemy.orm import Session
from app.config.settings import get_settings
from app.config.database import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.repositories.document import DocumentRepository
from app.repositories.chunk import ChunkRepository
from app.services.rag.parsing.parser import parse_file
from app.services.rag.chunking.hierarchy import hierarchy_chunk
from app.services.rag.metadata.extractor import extract_chunk_metadata, extract_document_metadata
from app.services.rag.metadata.summarizer import summarize_text
from app.services.rag.metadata.keywords import extract_keywords
from app.services.rag.embeddings.mistral import embed_texts
from app.services.rag.embeddings.duplicate import is_duplicate, mark_embedded
from app.services.rag.vectorstore.qdrant import ensure_collection
from app.services.rag.vectorstore.insert import insert_chunks
from loguru import logger

_settings = get_settings()


async def index_document(file_path: str, tenant_id: str, db: Session | None = None) -> str:
    """
    Full indexing pipeline for a single document.
    Returns document_id.
    """
    path = Path(file_path)
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # 1. Create document record
        doc_repo = DocumentRepository(db)
        doc = Document(
            tenant_id=tenant_id,
            filename=path.name,
            file_path=str(path),
            file_type=path.suffix.lower().lstrip("."),
            status="processing",
        )
        doc = doc_repo.create(doc)
        logger.info(f"Indexing document {doc.id}: {path.name}")

        # 2. Parse file
        pages = parse_file(file_path)
        doc.total_pages = len(pages)

        # 3. Chunk
        chunks_data = hierarchy_chunk(pages)
        logger.info(f"Created {len(chunks_data)} chunks")

        # 4. Extract metadata
        doc_meta = extract_document_metadata(pages)
        all_text = " ".join([c["text"] for c in chunks_data])
        keywords = extract_keywords(all_text, top_n=10)
        doc.keywords = ", ".join(keywords)

        # 5. Summarize (async)
        summary = await summarize_text(all_text[:10000])
        doc.summary = summary

        # 6. Embed chunks (skip duplicates)
        chunk_repo = ChunkRepository(db)
        chunk_records = []
        embeddings = []
        payloads = []
        chunk_ids = []

        for i, chunk_data in enumerate(chunks_data):
            text = chunk_data["text"]
            # Check duplicate
            dup_hash = is_duplicate(text)
            if dup_hash:
                continue

            # Create chunk record
            chunk = Chunk(
                id=chunk_data["chunk_id"],

                document_id=doc.id,

                tenant_id=tenant_id,

                chunk_index=i,

                text=text,

                page=chunk_data["page"],

                section=chunk_data.get("heading"),

                heading=chunk_data.get("heading"),

                parent_chunk_id=chunk_data.get("parent_chunk_id"),

                prev_chunk_id=chunk_data.get("prev_chunk_id"),

                next_chunk_id=chunk_data.get("next_chunk_id"),

                chunk_type=chunk_data.get("chunk_type"),

                section_path=chunk_data.get("section_path"),

                word_count=chunk_data.get("word_count"),

                tags=keywords[:5],

                permissions=[]
            )
            chunk_records.append(chunk)
            chunk_ids.append(chunk.id)

        # Bulk insert chunks to DB
        if chunk_records:
            chunk_repo.create_many(chunk_records)
            logger.info(f"Saved {len(chunk_records)} chunks to PostgreSQL")

            # Embed all chunk texts
            texts_to_embed = [c.text for c in chunk_records]
            embeddings = await embed_texts(texts_to_embed)

            # Mark as embedded in Redis
            for c in chunk_records:
                h = mark_embedded(c.text, c.id)
                c.embedding_hash = h

            # Build payloads for Qdrant
            for c in chunk_records:
                payloads.append({

                    "text": c.text,

                    "chunk_id": c.id,

                    "document_id": c.document_id,

                    "tenant_id": c.tenant_id,

                    "page": c.page,

                    "heading": c.heading,

                    "chunk_type": c.chunk_type,

                    "parent_chunk_id": c.parent_chunk_id,

                    "prev_chunk_id": c.prev_chunk_id,

                    "next_chunk_id": c.next_chunk_id,

                    "section_path": c.section_path,

                    "word_count": c.word_count,

                    "tags": c.tags
                })

                            # 7. Insert into Qdrant
            ensure_collection()
            insert_chunks(chunk_ids, embeddings, payloads)

        # Update document status
        doc_repo.update_summary(doc.id, summary, ", ".join(keywords), len(chunk_records))
        logger.info(f"Document {doc.id} indexed successfully: {len(chunk_records)} chunks")
        return doc.id

    except Exception as e:
        logger.error(f"Indexing failed for {file_path}: {e}")
        if 'doc' in locals():
            doc_repo.update_status(doc.id, "failed")
        raise
    finally:
        if close_db:
            db.close()
