from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import upload_router, chat_router, health_router, knowledge_review_router, orchestrator_router
from app.routers.conversation_memory import router as conversation_memory_router
from app.routers.onboarding import router as onboarding_router
from app.routers.channels_email import router as channels_email_router
from app.routers.website_ingestion import router as website_ingestion_router
from app.api.websocket_handler import router as websocket_router
from app.api.conversations.analysis import router as conversation_analysis_router
from app.routers.voice_test import router as voice_test_router
from app.services.rag.vectorstore.qdrant import ensure_collection
from app.config.kafka import ensure_topics
from loguru import logger


def create_app() -> FastAPI:
    app = FastAPI(title="Follei Backend", description="Enterprise RAG and business workforce API", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    for router in (upload_router, chat_router, health_router, knowledge_review_router, orchestrator_router, conversation_memory_router, onboarding_router, channels_email_router, website_ingestion_router, websocket_router, voice_test_router):
        app.include_router(router)

    # Restored working domain API surface from backup-before-cleanup.
    from app.routers import api_v1, conversation, customers, integrations, leads, message, tools, database_crud
    app.include_router(api_v1.router)
    app.include_router(conversation.router, prefix="/api")
    app.include_router(conversation_analysis_router, prefix="/api")
    app.include_router(message.router, prefix="/api")
    app.include_router(leads.router, prefix="/api")
    app.include_router(leads.frameworks_router, prefix="/api")
    app.include_router(leads.opportunities_router, prefix="/api")
    app.include_router(leads.meetings_router, prefix="/api")
    app.include_router(customers.router, prefix="/api")
    app.include_router(customers.renewals_router, prefix="/api")
    app.include_router(integrations.integrations_router, prefix="/api")
    app.include_router(integrations.connections_router, prefix="/api")
    app.include_router(integrations.webhooks_receive_router, prefix="/api")
    app.include_router(integrations.webhook_events_router, prefix="/api")
    app.include_router(tools.tools_router, prefix="/api")
    app.include_router(tools.executions_router, prefix="/api")
    app.include_router(tools.logs_router, prefix="/api")
    app.include_router(database_crud.router, prefix="/api")

    @app.on_event("startup")
    async def startup():
        logger.info("Starting up Follei backend...")
        try: ensure_collection()
        except Exception as exc: logger.warning(f"Qdrant init warning: {exc}")
        try: ensure_topics()
        except Exception as exc: logger.warning(f"Kafka init warning: {exc}")

    @app.get("/", tags=["System"])
    def root():
        return {"message": "Follei API Running", "docs": "/docs", "health": "/health/"}

    return app

app = create_app()
