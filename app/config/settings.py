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
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175"
    )

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
    MISTRAL_REQUEST_TIMEOUT_SECONDS: float = 60.0
    MISTRAL_EMBEDDING_BATCH_SIZE: int = 32
    AUTH_OTP_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    AUTH_OTP_REQUEST_LIMIT: int = Field(default=3, ge=1, le=20)
    AUTH_OTP_VERIFY_LIMIT: int = Field(default=5, ge=1, le=20)
    AUTH_OTP_RATE_WINDOW_SECONDS: int = Field(default=600, ge=60, le=3600)
    ENUMERABLE_THRESHOLD: int = Field(
        default=25,
        ge=1,
        le=10_000,
        description="Maximum category item count rendered as individually reviewable items by default.",
    )
    AI_MODELS: str = Field(default="AI_MODELS", description="Canonical local AI model root")
    # Local response generation. llama.cpp exposes an OpenAI-compatible API,
    # keeping model runtime concerns outside the FastAPI worker process.
    LOCAL_LLM_BASE_URL: str = "http://127.0.0.1:8081/v1"
    LOCAL_LLM_MODEL: str = "follei-qwen3-4b"
    # The canonical knowledge query path uses Mistral. Starting a local
    # llama.cpp process is an optional legacy/voice profile, never a core API
    # startup side effect.
    LOCAL_LLM_AUTO_START: bool = False
    LOCAL_LLM_SERVER_PATH: str = "AI_MODELS/llama.cpp/b10103/llama-server.exe"
    LOCAL_LLM_MODEL_PATH: str = "AI_MODELS/gguf/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    LOCAL_LLM_CONTEXT_SIZE: int = 8192
    LOCAL_LLM_STARTUP_TIMEOUT_SECONDS: float = 45.0
    LOCAL_LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0
    LOCAL_LLM_FILLER_DELAY_MS: int = 750

    # Ã¢â€â‚¬Ã¢â€â‚¬ Kafka Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_INDEXING: str = "document-indexing"
    KAFKA_TOPIC_INDEXING_DLQ: str = "document-indexing-dlq"
    KAFKA_TOPIC_CHAT: str = "chat-requests"
    KAFKA_TOPIC_WEBSITE_INGESTION: str = "website-ingestion"
    KAFKA_TOPIC_GOOGLE_WORKSPACE_SYNC: str = "google-workspace-sync"
    KAFKA_TOPIC_CRM_SYNC: str = "crm-sync"
    KAFKA_CONSUMER_GROUP: str = "follei-rag-group"
    KAFKA_INDEXING_MAX_ATTEMPTS: int = 3
    KAFKA_INGESTION_MAX_ATTEMPTS: int = 3

    # Ã¢â€â‚¬Ã¢â€â‚¬ RAG Pipeline Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 20
    KNOWLEDGE_QUERY_TOP_K: int = 8
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
    CRM_ENCRYPTION_KEY: str = Field(default="")
    FRONTEND_BASE_URL: str = Field(default="http://localhost:5173")
    FRONTEND_CRM_RETURN_PATH: str = Field(default="/settings/integrations/crm")
    SALESFORCE_CLIENT_ID: str = Field(default="")
    SALESFORCE_CLIENT_SECRET: str = Field(default="")
    HUBSPOT_CLIENT_ID: str = Field(default="")
    HUBSPOT_CLIENT_SECRET: str = Field(default="")
    HUBSPOT_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/crm/hubspot/oauth/callback")
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
    # Flash is ElevenLabs' latency-oriented multilingual voice model. The
    # provider remains swappable via streaming_tts_service.py.
    ELEVENLABS_TTS_MODEL: str = "eleven_flash_v2_5"
    ELEVENLABS_STT_MODEL: str = "scribe_v2"
    ELEVENLABS_STT_LANGUAGE: str = "auto"
    ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    ELEVENLABS_TIMEOUT_SECONDS: int = 60
    ELEVENLABS_FALLBACK_ENABLED: bool = True
    # Default True for now: the configured ElevenLabs key is out of free-tier
    # quota (0/10000 credits, resets 2026-08-10), so every TTS call was paying
    # a real ~0.5-1s network round trip to a call that always 401s before
    # falling back to gTTS anyway. Flip to False once the key has quota again
    # to resume trying ElevenLabs first for its higher-quality voices.
    TTS_SKIP_ELEVENLABS: bool = True

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
    GMAIL_CLIENT_ID: str = Field(default="")
    GMAIL_CLIENT_SECRET: str = Field(default="")
    GMAIL_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/email-connections/gmail/oauth/callback"
    )
    GMAIL_OAUTH_SUCCESS_URL: str = Field(default="http://localhost:8000/tenant")
    GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/integrations/google-workspace/oauth/callback"
    )
    GOOGLE_AUTH_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/auth/google/callback"
    )
    GMAIL_OAUTH_STATE_TTL_SECONDS: int = 600
    # Optional fallback tenant when an inbound sender matches no known lead.
    # Empty means "skip senders we can't map to a tenant".
    GMAIL_DEFAULT_TENANT_ID: str = Field(default="")
    # Encrypts per-tenant Gmail app passwords and Brevo keys stored in
    # PostgreSQL. Empty falls back to SECRET_KEY for local development.
    EMAIL_CREDENTIAL_ENCRYPTION_KEY: str = Field(default="")
    EMAIL_ATTACHMENT_MAX_BYTES: int = 10 * 1024 * 1024

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
