"""End-to-end chat pipeline: question → answer + citations + confidence."""
from app.services.rag.llm.optimizer import optimize_user_request
from app.services.rag.pipelines.retrieval import retrieve_context
from app.services.rag.llm.generator import generate_answer
from app.services.rag.llm.citations import extract_citations
from app.services.rag.verifier.confidence import verify_answer
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def chat_pipeline(question: str, tenant_id: str, session_id: str | None = None) -> dict:
    """
    Full RAG chat pipeline with AI Query Pre-Processing:
    1. Optimize user request (Fix typos, extract semantic keywords, build custom system prompt)
    2. Retrieve context chunks using the clean optimized query
    3. Generate candidate answer using the custom prompt constraints
    4. Verify correctness against context chunks
    5. Return validated payload
    """
    logger.info(f"Processing query for tenant_id: {tenant_id}")

    # 1. AI Pre-processing step: Rewrite query and get dynamic system prompt
    optimization = await optimize_user_request(question)
    search_query = optimization.get("optimized_search_query", question)
    tailored_system_prompt = optimization.get("tailored_system_prompt")

    logger.debug(f"Raw query rewritten to clean search query: '{search_query}'")

    # 2. Retrieve context using the CLEAN rewritten query vector text
    context, chunk_ids = await retrieve_context(search_query, tenant_id)

    if not context:
        logger.warning(f"No semantic contexts matched search query for tenant: {tenant_id}")
        return {
            "answer": "I don't have enough information to answer that question.",
            "citations": [],
            "confidence": 0.0,
            "supported": False,
            "reason": "No relevant documents found.",
        }

    # 3. Generate candidate answer (Pass original question, extracted context, and custom prompt rules)
    answer = await generate_answer(
        question=question, 
        context=context, 
        system_prompt=tailored_system_prompt
    )

    # 4. Verify candidate answer against retrieved context text blocks
    verification = await verify_answer(question, context, answer)

    # 5. If confidence is too low or claims fail verification, return the fallback block safely
    if verification["confidence"] < _settings.MIN_CONFIDENCE or not verification["supported"]:
        logger.warning(f"Pipeline verification rejected answer. Reason: {verification['reason']}")
        return {
            "answer": "I don't have enough information to answer that question confidently.",
            "citations": [],
            "confidence": verification["confidence"],
            "supported": verification["supported"],
            "reason": verification["reason"],
        }

    # 6. Extract document citations from matched chunks if valid
    citations = extract_citations(chunk_ids)

    logger.info(f"Pipeline successfully verified answer with confidence: {verification['confidence']}")
    return {
        "answer": answer,
        "citations": citations,
        "confidence": verification["confidence"],
        "supported": verification["supported"],
        "reason": verification["reason"],
    }