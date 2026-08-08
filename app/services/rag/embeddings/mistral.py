"""Backward-compatible imports for the canonical Mistral embedding adapter."""
from app.services.knowledge.embedding_service import embed_query, embed_texts

__all__ = ["embed_query", "embed_texts"]
