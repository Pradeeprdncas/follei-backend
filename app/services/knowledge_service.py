"""Knowledge service — manages documents, chunks, entities."""
from uuid import UUID
from typing import Any
from sqlalchemy.orm import Session
from app.repositories.document import DocumentRepository
from app.repositories.chunk import ChunkRepository
from app.repositories.base import BaseRepository
from app.models.knowledge.document import Document, DocumentChunk, ChunkEmbedding
from app.models.knowledge.entity import Entity, EntityAlias, EntityAttribute, EntityRelation


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.chunk_repo = ChunkRepository(db)

    def get_document(self, doc_id: UUID) -> Document:
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    def list_documents(self, tenant_id: UUID) -> list[Document]:
        return self.doc_repo.get_by_tenant(tenant_id)

    def create_chunk_embedding(self, chunk_id: UUID, tenant_id: UUID,
                               model: str, vector: list[float]) -> ChunkEmbedding:
        chunk = self.db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id, DocumentChunk.tenant_id == tenant_id
        ).first()
        if not chunk:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Chunk not found")
        existing = self.db.query(ChunkEmbedding).filter(
            ChunkEmbedding.chunk_id == chunk.id,
            ChunkEmbedding.tenant_id == tenant_id,
            ChunkEmbedding.embedding_model == model,
        ).first()
        if existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Embedding already exists for this model")
        embedding = ChunkEmbedding(
            chunk_id=chunk.id, tenant_id=tenant_id,
            embedding_model=model, embedding=vector,
        )
        self.db.add(embedding)
        self.db.commit()
        self.db.refresh(embedding)
        return embedding

    def list_chunk_embeddings(self, chunk_id: UUID, tenant_id: UUID) -> list[ChunkEmbedding]:
        return self.db.query(ChunkEmbedding).filter(
            ChunkEmbedding.chunk_id == chunk_id,
            ChunkEmbedding.tenant_id == tenant_id,
        ).all()

    def delete_chunk_embedding(self, embedding_id: UUID, tenant_id: UUID) -> None:
        embedding = self.db.query(ChunkEmbedding).filter(
            ChunkEmbedding.id == embedding_id,
            ChunkEmbedding.tenant_id == tenant_id,
        ).first()
        if not embedding:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Embedding not found")
        self.db.delete(embedding)
        self.db.commit()
