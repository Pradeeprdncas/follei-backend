from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
from swagger_ui_bundle import swagger_ui_path
from app.routers import upload_router, chat_router, health_router, knowledge_review_router, orchestrator_router
from app.routers.conversation_memory import router as conversation_memory_router
from app.routers.onboarding import router as onboarding_router
from app.routers.channels_email import router as channels_email_router
from app.routers.website_ingestion import router as website_ingestion_router
from app.api.websocket_handler import router as websocket_router
from app.api.conversations.analysis import router as conversation_analysis_router
from app.routers.voice_test import router as voice_test_router
from app.routers.verification_ui import router as verification_ui_router
from app.routers.flows import router as flows_router, assets_router
from app.routers.email_connections import router as email_connections_router
from app.routers.channel_connections import router as channel_connections_router
from app.api.campaigns import router as campaigns_router
from app.routers.crm_sync import router as crm_sync_router
from app.services.rag.vectorstore.qdrant import ensure_collection
from app.config.kafka import ensure_topics
from loguru import logger


def create_app() -> FastAPI:
    app = FastAPI(
        title="Follei Backend",
        description="Enterprise RAG and business workforce API",
        version="1.0.0",
        docs_url=None,
    )
    app.mount("/api-docs-assets", StaticFiles(directory=str(swagger_ui_path)), name="api-docs-assets")

    @app.get("/docs", include_in_schema=False)
    async def swagger_docs():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="/api-docs-assets/swagger-ui-bundle.js",
            swagger_css_url="/api-docs-assets/swagger-ui.css",
            swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    async def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    for router in (upload_router, chat_router, health_router, knowledge_review_router, orchestrator_router, conversation_memory_router, onboarding_router, channels_email_router, website_ingestion_router, websocket_router, voice_test_router, verification_ui_router, email_connections_router, channel_connections_router, flows_router, assets_router, crm_sync_router):
        app.include_router(router)
    app.include_router(campaigns_router, prefix="/api/v1")

    # Restored working domain API surface from backup-before-cleanup.
    from app.routers import api_v1, conversation, customers, integrations, leads, message, tools, database_crud
    from app.domains.lead_import.router import router as lead_import_router
    app.include_router(api_v1.router)
    app.include_router(conversation.router, prefix="/api")
    app.include_router(conversation_analysis_router, prefix="/api")
    app.include_router(message.router, prefix="/api")
    app.include_router(leads.router, prefix="/api")
    app.include_router(leads.frameworks_router, prefix="/api")
    app.include_router(leads.opportunities_router, prefix="/api")
    app.include_router(leads.meetings_router, prefix="/api")
    app.include_router(lead_import_router, prefix="/api")
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
        from app.services.ai.local_llm_server import ensure_local_llm_server
        try:
            await ensure_local_llm_server()
        except Exception as exc:
            logger.warning(f"Local response model startup warning: {exc}")
        try: ensure_collection()
        except Exception as exc: logger.warning(f"Qdrant init warning: {exc}")
        try: ensure_topics()
        except Exception as exc: logger.warning(f"Kafka init warning: {exc}")

    @app.get("/", tags=["System"])
    def root():
        return {"message": "Follei API Running", "docs": "/docs", "health": "/health/"}

    return app

app = create_app()
