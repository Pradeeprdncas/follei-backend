"""Centralized Pydantic Settings for the entire backend."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """All environment variables loaded from .env."""

    # â”€â”€ App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(default="change-me", description="JWT / session secret")

    # â”€â”€ PostgreSQL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/follei")

    # â”€â”€ Redis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    REDIS_URL: str = Field(default="redis://localhost:6379")
    FERRETDB_URL: str = Field(default="mongodb://localhost:27017/ferret_context")
    FERRETDB_DATABASE: str = Field(default="ferret_context")
    FERRETDB_USER: str = Field(default="")
    FERRETDB_PASSWORD: str = Field(default="")

    # â”€â”€ Qdrant â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    QDRANT_URL: str = Field(default="http://localhost:6333")
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "follei_chunks"
    QDRANT_VECTOR_SIZE: int = 1024  # Mistral embedding dimension

    # â”€â”€ Mistral LLM / Embeddings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    MISTRAL_API_KEY: str = Field(default="")
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"
    MISTRAL_CHAT_MODEL: str = "mistral-medium-2508"
    MISTRAL_API_BASE: str = "https://api.mistral.ai/v1"

    # â”€â”€ Kafka â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_INDEXING: str = "document-indexing"
    KAFKA_TOPIC_CHAT: str = "chat-requests"
    KAFKA_CONSUMER_GROUP: str = "follei-rag-group"

    # â”€â”€ RAG Pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
