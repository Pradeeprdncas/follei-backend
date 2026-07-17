"""BM25 keyword retrieval from PostgreSQL."""
from rank_bm25 import BM25Okapi
from app.repositories.chunk import ChunkRepository
from app.config.database import SessionLocal
from app.services.rag.retrieval.approval import chunk_tags_approved
from loguru import logger
import re


def tokenize(text: str) -> list[str]:
    """
    Robust alphanumeric word tokenizer.
    Cleans special characters and extracts clean text strings.
    """
    if not text:
        return []
    # FIX: Uses clean raw-string syntax to match any string sequence of words safely
    return re.findall(r'[a-z0-9]+', text.lower())


def retrieve_bm25(query: str, tenant_id: str, top_k: int = 20) -> list[dict]:
    """
    BM25 retrieval over chunk texts stored in PostgreSQL.
    Returns list of {"chunk_id", "score", "payload": {"text": str}}.
    """
    db = SessionLocal()
    try:
        repo = ChunkRepository(db)
        all_chunks = repo.get_texts_for_bm25(tenant_id)
        # Unconditional approval filter: unlike Qdrant's keyword-conditional check,
        # Postgres chunk text has no per-query approval signal to weigh against, so
        # draft/unapproved chunk text must never reach BM25 scoring at all.
        rows = [c for c in all_chunks if chunk_tags_approved(c.tags)]

        if not rows:
            logger.warning(f"No approved chunks found for tenant={tenant_id}")
            return []

        # Parse text chunks cleanly
        chunk_ids = [r.id for r in rows]
        texts = [r.content if r.content is not None else "" for r in rows]
        tokenized = [tokenize(t) for t in texts]

        # FIX: Safety Guard — If text extraction yields zero valid tokens across all items,
        # fallback to avoid crashing BM25Okapi instantiation with a 0 average length.
        total_tokens = sum(len(tokens) for tokens in tokenized)
        if total_tokens == 0:
            logger.warning("BM25 Tokenizer yielded 0 total tokens across all rows. Aborting keyword match stage.")
            return []

        bm25 = BM25Okapi(tokenized)
        query_tokens = tokenize(query)
        
        if not query_tokens:
            return []

        scores = bm25.get_scores(query_tokens)

        # Sort by score descending
        scored = sorted(zip(chunk_ids, scores, texts), key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        results = []
        for cid, score, text in top:
            # FIX: Ensure we accept valid low matches safely while parsing out float wrappers
            if score > 0:
                results.append({
                    "chunk_id": str(cid),
                    "score": float(score),
                    # Ensure matching payload fields match what rrf.py expects
                    "text": text,
                    "payload": {"text": text}
                })

        logger.info(f"BM25 retrieval: {len(results)} chunks for query='{query[:50]}...'")
        return results
    except Exception as e:
        logger.error(f"BM25 Retrieval process failed due to error: {str(e)}")
        return []
    finally:
        db.close()