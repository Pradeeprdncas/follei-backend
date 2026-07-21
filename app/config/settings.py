"""Centralized Pydantic Settings for the entire backend."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """All environment variables loaded from .env."""

    # Ã¢â€â‚¬Ã¢â€â‚¬ App Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(default="change-me", description="JWT / session secret")
    SERVICE_TIMEOUT: int = 60  # default outbound HTTP timeout (seconds)

    # Ã¢â€â‚¬Ã¢â€â‚¬ PostgreSQL Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/follei")

    # Ã¢â€â‚¬Ã¢â€â‚¬ Redis Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    REDIS_URL: str = Field(default="redis://localhost:6379")
    FERRETDB_URL: str = Field(default="mongodb://localhost:27017/ferret_context")
    FERRETDB_DATABASE: str = Field(default="ferret_context")
    FERRETDB_USER: str = Field(default="")
    FERRETDB_PASSWORD: str = Field(default="")
    OBJECT_STORAGE_ENABLED: bool = False
    OBJECT_STORAGE_ENDPOINT_URL: str = "http://localhost:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "follei"
    OBJECT_STORAGE_SECRET_KEY: str = "follei-local-object-storage"
    OBJECT_STORAGE_BUCKET: str = "follei-uploads"
    OBJECT_STORAGE_REGION: str = "us-east-1"

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
    AI_MODELS: str = Field(default="AI_MODELS", description="Canonical local AI model root")

    # Ã¢â€â‚¬Ã¢â€â‚¬ Kafka Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_INDEXING: str = "document-indexing"
    KAFKA_TOPIC_INDEXING_DLQ: str = "document-indexing-dlq"
    KAFKA_TOPIC_CHAT: str = "chat-requests"
    KAFKA_CONSUMER_GROUP: str = "follei-rag-group"
    KAFKA_INDEXING_MAX_ATTEMPTS: int = 3

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
    # Empty by default (dev). Set to require the X-Webhook-Secret header on
    # POST /channels/email/inbound before it's exposed to a real provider.
    EMAIL_INBOUND_WEBHOOK_SECRET: str = Field(default="")

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

    # -- Local AI model names (app/core/bootstrap.py, app/services/ai/runtime/*) --
    EMBED_MODEL: str = "nomic-embed-text-v1.5"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    INTENT_MODEL: str = "ModernBERT-base"
    QUERY_MODEL: str = "qwen2.5-0.5b"
    SUMMARY_MODEL: str = "smollm2-360m"
    GENERATOR_MODEL: str = "qwen2.5-3b-instruct"
    RERANK_MODEL: str = "bge-reranker-base"
    MODEL_BASE: str = "Qwen/Qwen2.5-3B-Instruct"
    LORA_MODEL: str = "qwen3b-follei"
    LORA_OUTPUT_DIR: str = "./models/lora-qwen3b"
    VOICE_PRELOAD_MODELS: bool = False
    VOICE_PRELOAD_MAIN_MODEL: bool = False

    # -- Local model inference parameters (app/analysis/services/model_service.py, tokenizer.py) --
    MAX_HISTORY: int = 20
    MAX_TOKENS: int = 1024
    MAX_NEW_TOKENS: int = 512
    TEMPERATURE: float = 0.3
    TOP_P: float = 0.95

    # -- Kafka domain events (app/analysis pipeline + every app/workers/*.py consumer) --
    KAFKA_TOPIC_DOMAIN_EVENTS: str = "domain-events"
    KAFKA_CONSUMER_GROUP_ANALYSIS: str = "follei-analysis-group"

    # -- Voice: STT/TTS provider + audio handling (app/api/websocket_handler.py) --
    SPEECH_TO_TEXT_PROVIDER: str = "elevenlabs"
    MAX_VOICE_AUDIO_SECONDS: int = 120
    ENABLE_NOISE_REDUCTION: bool = True
    DEBUG_SAVE_AUDIO: bool = False
    TTS_OUTPUT_DIR: str = "./tts_output"

    # -- ElevenLabs (app/analysis/services/elevenlabs_service.py, tts_service.py) --
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_VOICE_ID: str = Field(default="")
    ELEVENLABS_MALE_VOICE_ID: str = Field(default="")
    ELEVENLABS_FEMALE_VOICE_ID: str = Field(default="")
    ELEVENLABS_TAMIL_VOICE_ID: str = Field(default="")
    ELEVENLABS_TTS_MODEL: str = "eleven_multilingual_v2"
    ELEVENLABS_STT_MODEL: str = "scribe_v2"
    ELEVENLABS_STT_LANGUAGE: str = "auto"
    ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    ELEVENLABS_TIMEOUT_SECONDS: int = 60
    ELEVENLABS_FALLBACK_ENABLED: bool = True

    # -- Brevo email (transactional send + inbound auto-reply) --
    BREVO_API_KEY: str = Field(default="")
    BREVO_SENDER_EMAIL: str = Field(default="")
    BREVO_SENDER_NAME: str = Field(default="Follei")
    BREVO_AUTO_REPLY_ENABLED: bool = True
    BREVO_AUTO_REPLY_CONFIDENCE_THRESHOLD: float = 0.6
    BREVO_AUTO_REPLY_RATE_LIMIT: int = 10
    BREVO_INBOUND_DOMAIN: str = Field(default="")

    # -- Gmail IMAP/SMTP auto-reply (app-password based) --
    GMAIL_MONITORED_EMAIL: str = Field(default="")
    GMAIL_APP_PASSWORD: str = Field(default="")
    GMAIL_IMAP_HOST: str = "imap.gmail.com"
    GMAIL_SMTP_HOST: str = "smtp.gmail.com"
    GMAIL_SMTP_PORT: int = 465
    GMAIL_POLL_INTERVAL_SECONDS: int = 60
    GMAIL_AUTO_REPLY_ENABLED: bool = True
    # Optional fallback tenant when an inbound sender matches no known lead.
    # Empty means "skip senders we can't map to a tenant".
    GMAIL_DEFAULT_TENANT_ID: str = Field(default="")

    # -- SMS provider selection: "twilio" (default) or "brevo" --
    SMS_PROVIDER: str = "twilio"

    # -- Twilio SMS + WhatsApp --
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_FROM_PHONE: str = Field(default="")
    SMS_DEFAULT_COUNTRY_CODE: str = "91"
    WHATSAPP_API_TOKEN: str = Field(default="")
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="")
    WHATSAPP_VERIFY_TOKEN: str = Field(default="")

    # -- CRM live-context enrichment (app/analysis/services/context_service.py) --
    CRM_API_URL: str = Field(default="")
    CRM_API_TOKEN: str = Field(default="")
    CRM_CONTEXT_PATH: str = Field(default="")
    BUSINESS_CONTEXT_PATH: str = Field(default="")
    CONTEXT_TIMEOUT_SECONDS: float = 10.0

    # -- AI response cache (app/services/ai/cache.py) --
    AI_CACHE_TTL: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
