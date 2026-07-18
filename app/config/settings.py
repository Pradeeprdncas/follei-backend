"""Centralized Pydantic Settings for the entire backend."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """All environment variables loaded from .env."""

    # Ã¢â€â‚¬Ã¢â€â‚¬ App Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(default="change-me", description="JWT / session secret")

    # Ã¢â€â‚¬Ã¢â€â‚¬ PostgreSQL Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/follei")

    # Ã¢â€â‚¬Ã¢â€â‚¬ Redis Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    REDIS_URL: str = Field(default="redis://localhost:6379")
    FERRETDB_URL: str = Field(default="mongodb://localhost:27017/ferret_context")
    FERRETDB_DATABASE: str = Field(default="ferret_context")
    FERRETDB_USER: str = Field(default="")
    FERRETDB_PASSWORD: str = Field(default="")

    # Ã¢â€â‚¬Ã¢â€â‚¬ Qdrant Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    QDRANT_URL: str = Field(default="http://localhost:6333")
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "follei_chunks"
    QDRANT_VECTOR_SIZE: int = 1024  # Mistral embedding dimension

    # Ã¢â€â‚¬Ã¢â€â‚¬ Mistral LLM / Embeddings Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    MISTRAL_API_KEY: str = Field(default="")
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"
    MISTRAL_CHAT_MODEL: str = "mistral-medium-2508"
    MISTRAL_API_BASE: str = "https://api.mistral.ai/v1"

    # Ã¢â€â‚¬Ã¢â€â‚¬ Kafka Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_INDEXING: str = "document-indexing"
    KAFKA_TOPIC_CHAT: str = "chat-requests"
    KAFKA_CONSUMER_GROUP: str = "follei-rag-group"

    # Ã¢â€â‚¬Ã¢â€â‚¬ RAG Pipeline Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 20
    TOP_K_RERANK: int = 5
    RRF_K: int = 60
    MIN_CONFIDENCE: float = 0.5
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_ANSWER_TOKENS: int = 4096
    # Fast call-path defaults. Expensive LLM rewrite/expansion/verification are opt-in.
    RAG_ENABLE_QUERY_OPTIMIZATION: bool = False
    RAG_ENABLE_QUERY_EXPANSION: bool = False
    RAG_ENABLE_LLM_VERIFICATION: bool = False
    RAG_QUERY_VARIANTS: int = 1
    RAG_QUERY_CACHE_TTL_SECONDS: int = 300
    RAG_ENABLE_DOCUMENT_CLASSIFICATION: bool = True
    CONVERSATION_SUMMARY_TURN_INTERVAL: int = 6

    # -- System 3-6 recovery: revenue intelligence / CRM integrations --
    BANT_MODEL_PATH: str = Field(default="AI_MODELS/bant")
    CRM_ENCRYPTION_KEY: str = Field(default="change-me-crm-encryption-key")
    FRONTEND_BASE_URL: str = Field(default="http://localhost:3000")
    FRONTEND_CRM_RETURN_PATH: str = Field(default="/settings/integrations/crm")
    SALESFORCE_CLIENT_ID: str = Field(default="")
    SALESFORCE_CLIENT_SECRET: str = Field(default="")
    HUBSPOT_CLIENT_ID: str = Field(default="")
    HUBSPOT_CLIENT_SECRET: str = Field(default="")
    ZOHO_CLIENT_ID: str = Field(default="")
    ZOHO_CLIENT_SECRET: str = Field(default="")
    ZOHO_ACCOUNTS_DOMAIN: str = Field(default="https://accounts.zoho.com")
    MICROSOFT_CLIENT_ID: str = Field(default="")
    MICROSOFT_CLIENT_SECRET: str = Field(default="")
    MICROSOFT_TENANT: str = Field(default="common")
    PIPEDRIVE_CLIENT_ID: str = Field(default="")
    PIPEDRIVE_CLIENT_SECRET: str = Field(default="")
    FRESHSALES_CLIENT_ID: str = Field(default="")
    FRESHSALES_CLIENT_SECRET: str = Field(default="")
    FRESHSALES_ACCOUNTS_DOMAIN: str = Field(default="https://your-domain.freshsales.io")
    COPPER_CLIENT_ID: str = Field(default="")
    COPPER_CLIENT_SECRET: str = Field(default="")
    KEAP_CLIENT_ID: str = Field(default="")
    KEAP_CLIENT_SECRET: str = Field(default="")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()



