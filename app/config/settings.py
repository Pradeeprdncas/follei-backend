"""Centralized Pydantic Settings for the entire backend."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """All environment variables loaded from .env."""

    # ── App ─────────────────────────────────
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(default="change-me", description="JWT / session secret")

    # ── PostgreSQL ──────────────────────────
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/follei")

    # ── Redis ─────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379")

    # ── Qdrant ────────────────────────────────
    QDRANT_URL: str = Field(default="http://localhost:6333")
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "follei_chunks"
    QDRANT_VECTOR_SIZE: int = 1024  # Mistral embedding dimension

    # ── Mistral LLM / Embeddings ────────────
    MISTRAL_API_KEY: str = Field(default="")
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"
    MISTRAL_CHAT_MODEL: str = "mistral-medium"
    MISTRAL_API_BASE: str = "https://api.mistral.ai/v1"

    # ── Kafka ─────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_INDEXING: str = "document-indexing"
    KAFKA_TOPIC_CHAT: str = "chat-requests"
    KAFKA_CONSUMER_GROUP: str = "follei-rag-group"

    # ── RAG Pipeline ──────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 20
    TOP_K_RERANK: int = 5
    RRF_K: int = 60
    MIN_CONFIDENCE: float = 0.5
    MAX_CONTEXT_TOKENS: int = 4000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
