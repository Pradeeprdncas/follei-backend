"""End-to-end chat pipeline: question -> answer + citations + confidence."""
from uuid import uuid4
from app.services.rag.llm.optimizer import optimize_user_request
from app.services.rag.pipelines.retrieval import retrieve_context
from app.services.rag.llm.generator import generate_answer
from app.services.rag.llm.citations import extract_citations
from app.services.rag.verifier.confidence import verify_answer
from app.services.rag.telemetry import LatencyTrace
from app.config.settings import get_settings
from app.config.database import SessionLocal
from app.services.knowledge.conversation_memory import ConversationScopeError, persist_chat_turn, summarize_conversation
from loguru import logger

_settings = get_settings()


async def chat_pipeline(question: str, tenant_id: str, session_id: str | None = None) -> dict:
    """Run a grounded answer path and emit one stage-by-stage latency trace."""
    trace = LatencyTrace(trace_id=session_id or str(uuid4()), tenant_id=tenant_id)
    try:
        if _settings.RAG_ENABLE_QUERY_OPTIMIZATION:
            optimization = await optimize_user_request(question)
            search_query = optimization.get("optimized_search_query", question)
            tailored_system_prompt = optimization.get("tailored_system_prompt")
        else:
            search_query = question
            tailored_system_prompt = "Answer only from the supplied context. Do not invent facts."
        trace.mark("query_optimize")

        context, chunk_ids = await retrieve_context(search_query, tenant_id)
        trace.mark("retrieve_context")
        if not context:
            result = {"answer": "I don't have enough information to answer that question.", "citations": [], "confidence": 0.0, "supported": False, "reason": "No relevant documents found."}
        else:
            answer = await generate_answer(question=question, context=context, system_prompt=tailored_system_prompt)
            trace.mark("answer_llm")

            if _settings.RAG_ENABLE_LLM_VERIFICATION:
                verification = await verify_answer(question, context, answer)
            else:
                verification = {"supported": True, "confidence": 0.7, "reason": "Grounded answer produced from retrieved context; LLM verification disabled for the fast path."}
            trace.mark("verify")

            if verification["confidence"] < _settings.MIN_CONFIDENCE or not verification["supported"]:
                result = {"answer": "I don't have enough information to answer that question confidently.", "citations": [], "confidence": verification["confidence"], "supported": verification["supported"], "reason": verification["reason"]}
            else:
                citations = extract_citations(chunk_ids)
                trace.mark("citations")
                result = {"answer": answer, "citations": citations, "confidence": verification["confidence"], "supported": verification["supported"], "reason": verification["reason"]}

        db = SessionLocal()
        try:
            conversation = persist_chat_turn(db, tenant_id=tenant_id, session_id=session_id, question=question, **result)
            result["conversation_id"] = str(conversation.id)
        except ConversationScopeError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.warning(f"Chat answer returned without durable conversation persistence: {exc}")
        finally:
            db.close()
        return result
    finally:
        trace.emit()


