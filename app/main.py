"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import upload_router, chat_router, health_router
from app.services.rag.vectorstore.qdrant import ensure_collection
from app.config.kafka import ensure_topics
from loguru import logger


def create_app() -> FastAPI:
    app = FastAPI(
        title="Follei Backend",
        description="Enterprise RAG backend with FastAPI, Kafka, Qdrant, PostgreSQL, Redis",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(upload_router)
    app.include_router(chat_router)
    app.include_router(health_router)

    @app.on_event("startup")
    async def startup():
        logger.info("Starting up Follei backend...")
        try:
            ensure_collection()
            logger.info("Qdrant collection ready")
        except Exception as e:
            logger.warning(f"Qdrant init warning: {e}")
        try:
            ensure_topics()
            logger.info("Kafka topics ready")
        except Exception as e:
            logger.warning(f"Kafka init warning: {e}")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down Follei backend...")

    return app


app = create_app()
