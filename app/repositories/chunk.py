"""Chunk repository — CRUD + text retrieval."""
from sqlalchemy.orm import Session
from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, chunk: Chunk) -> Chunk:
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def create_many(self, chunks: list[Chunk]) -> None:
        self.db.bulk_save_objects(chunks)
        self.db.commit()

    def get_by_id(self, chunk_id: str) -> Chunk | None:
        return self.db.query(Chunk).filter(Chunk.id == chunk_id).first()

    def get_by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        return self.db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()

    def get_by_document(self, doc_id: str) -> list[Chunk]:
        return self.db.query(Chunk).filter(Chunk.document_id == doc_id).order_by(Chunk.chunk_index).all()

    def get_by_tenant(self, tenant_id: str) -> list[Chunk]:
        return self.db.query(Chunk).filter(Chunk.tenant_id == tenant_id).all()

    def get_texts_for_bm25(self, tenant_id: str) -> list[tuple[str, str]]:
        """Return (chunk_id, text) for BM25 indexing."""
        rows = self.db.query(Chunk.id, Chunk.text).filter(Chunk.tenant_id == tenant_id).all()
        return [(r[0], r[1]) for r in rows]

    def get_by_embedding_hash(self, embedding_hash: str) -> Chunk | None:
        return self.db.query(Chunk).filter(Chunk.embedding_hash == embedding_hash).first()
