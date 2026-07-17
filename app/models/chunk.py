"""Canonical DocumentChunk compatibility export for the RAG pipeline."""
from app.models.document import Document
from app.models.knowledge.document import DocumentChunk as Chunk

__all__ = ["Chunk", "Document"]
