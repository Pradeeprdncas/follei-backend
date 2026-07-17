import logging

from app.config.settings import get_settings
from app.config.qdrant import get_qdrant
from app.services.rag.vectorstore.search import dense_search

_settings = get_settings()

logger = logging.getLogger(__name__)


class RAGService:
    initialized = False

    @classmethod
    def initialize(cls):
        try:
            get_qdrant()
            cls.initialized = True
            logger.info("RAG retrieval service initialized (Qdrant)")
        except Exception as e:
            logger.warning("RAG service initialization failed: %s", str(e))
            cls.initialized = False

    @classmethod
    async def retrieve(cls, query: str, top_k: int = 5, tenant_id: str = "default"):
        if not cls.initialized:
            logger.debug("RAG service not initialized. Returning empty results.")
            return []
        try:
            from app.services.rag.embeddings.local import embed_texts
            vectors = await embed_texts([query])
            query_vector = vectors[0] if vectors else []
        except ImportError:
            logger.debug("Embedding function not available, skipping RAG")
            return []
        if not query_vector:
            return []
        results = dense_search(query_vector=query_vector, tenant_id=tenant_id, top_k=top_k)
        docs = [item["payload"].get("text", "") for item in results if item.get("payload")]
        docs = [doc for doc in docs if doc]
        logger.debug("RAG retrieved %d docs", len(docs))
        return docs
