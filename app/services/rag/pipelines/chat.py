"""End-to-end chat pipeline: question -> answer + citations + confidence."""
import json
from uuid import uuid4
from app.services.rag.llm.optimizer import optimize_user_request
from app.services.rag.pipelines.retrieval import retrieve_context
from app.services.rag.llm.generator import generate_answer
from app.services.rag.llm.citations import extract_citations
from app.services.rag.verifier.confidence import verify_answer
from app.services.rag.telemetry import LatencyTrace
from app.config.settings import get_settings
from app.config.database import SessionLocal
from app.services.knowledge.orchestrator import build_agent_context
from app.services.knowledge.conversation_memory import ConversationScopeError, persist_chat_turn, summarize_conversation
from loguru import logger
from app.models.domain import RetrievalLog

_settings = get_settings()

_MAX_FACTS_IN_CONTEXT = 5


def _json_safe(value):
    """Convert UUIDs and other scalar identifiers into JSON-safe values."""
    return json.loads(json.dumps(value, default=str))


def _format_agent_context(agent_context: dict) -> str:
    """Render orchestrator facts/customer memory as an extra grounded-context block."""
    sections: list[str] = []
    approved = (agent_context.get("facts") or {}).get("approved") or []
    if approved:
        lines = [
            f"- ({fact.get('fact_type')}) {fact.get('topic')}: {fact.get('value')}"
            for fact in approved[:_MAX_FACTS_IN_CONTEXT]
        ]
        sections.append("APPROVED BUSINESS FACTS (source: Postgres, human-approved):\n" + "\n".join(lines))
    relationships = agent_context.get("relationships") or []
    if relationships:
        sections.append("KNOWLEDGE GRAPH RELATIONSHIPS (source: Postgres graph):\n" + "\n".join(
            f"- {item.get('from')} {item.get('relation')} {item.get('to')}"
            for item in relationships[:_MAX_FACTS_IN_CONTEXT]
        ))
    customer_context = agent_context.get("customer_context") or {}
    if customer_context:
        sections.append(f"CUSTOMER CONTEXT (source: FerretDB memory): {customer_context}")
    memory_evidence = agent_context.get("memory_evidence") or []
    if memory_evidence:
        sections.append("LONG-TERM DOCUMENT MEMORY (source: FerretDB clean projections):\n" + "\n".join(
            f"- {item.get('title')}: {item.get('summary')}"
            for item in memory_evidence[:3]
        ))
    return "\n\n".join(sections)


def _fact_citations(agent_context: dict) -> list[dict]:
    """Citations for approved Postgres facts, distinct from raw Qdrant chunk citations."""
    approved = (agent_context.get("facts") or {}).get("approved") or []
    return [
        {
            "source": "postgres_fact",
            "fact_id": fact.get("fact_id"),
            "fact_type": fact.get("fact_type"),
            "topic": fact.get("topic"),
            "citation": fact.get("citation"),
        }
        for fact in approved[:_MAX_FACTS_IN_CONTEXT]
    ]


def _graph_citations(agent_context: dict) -> list[dict]:
    return [{"source": "graph_relation", "from": item.get("from"), "relation": item.get("relation"), "to": item.get("to"), "citation": item.get("citation"), "trust_rank": item.get("trust_rank")} for item in (agent_context.get("relationships") or []) if item.get("source") == "graph"]


def _memory_citations(agent_context: dict) -> list[dict]:
    memory = agent_context.get("customer_context") or {}
    citations = [{"source": "ferretdb_memory", "subject_type": memory.get("subject_type"), "subject_id": memory.get("subject_id"), "freshness_at": memory.get("freshness_at"), "trust_rank": memory.get("trust_rank")}] if memory else []
    citations.extend({
        "source": "ferretdb_document_memory",
        "document_id": item.get("document_id"),
        "document_name": item.get("title"),
        "category": item.get("category"),
        "projection_type": item.get("projection_type"),
        "freshness_at": item.get("freshness_at"),
        "trust_rank": item.get("trust_rank"),
    } for item in (agent_context.get("memory_evidence") or []))
    return citations


def _chunk_citations(chunk_ids: list[str]) -> list[dict]:
    return [{**citation, "source": citation.get("source") or "qdrant_chunk"} for citation in extract_citations(chunk_ids)]


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

        # Merge orchestrator context: approved Postgres facts, graph relationships,
        # and FerretDB customer/lead memory are layered on top of hybrid chunk
        # retrieval rather than replacing it — build_agent_context()'s own
        # "evidence" field is dense-only and would drop BM25/rerank/neighbor
        # expansion coverage if used as a substitute for retrieve_context().
        orchestrator_db = SessionLocal()
        try:
            agent_context = await build_agent_context(db=orchestrator_db, tenant_id=tenant_id, query=search_query)
        except Exception as exc:
            logger.warning(f"Orchestrator context unavailable, continuing with hybrid retrieval only: {exc}")
            agent_context = {"facts": {"approved": []}, "relationships": [], "customer_context": {}, "conflicts": []}
        finally:
            orchestrator_db.close()
        trace.mark("orchestrator_context")

        agent_context_text = _format_agent_context(agent_context)
        combined_context = "\n\n".join(part for part in (agent_context_text, context) if part)
        conflicts = agent_context.get("conflicts") or []

        if not combined_context:
            result = {"answer": "I don't have enough information to answer that question.", "citations": [], "confidence": 0.0, "supported": False, "reason": "No relevant documents found.", "conflicts": []}
        elif conflicts:
            # Approved Postgres facts disagree for this question's topic. Never let
            # the LLM silently pick one side — surface the conflict instead of an answer.
            result = {
                "answer": "Multiple approved records disagree on this; it needs human review before I can answer confidently.",
                "citations": _fact_citations(agent_context),
                "confidence": 0.0,
                "supported": False,
                "reason": "Conflicting approved facts require human review.",
                "conflicts": conflicts,
            }
        else:
            answer = await generate_answer(question=question, context=combined_context, system_prompt=tailored_system_prompt)
            trace.mark("answer_llm")

            if _settings.RAG_ENABLE_LLM_VERIFICATION:
                verification = await verify_answer(question, combined_context, answer)
            else:
                verification = {"supported": True, "confidence": 0.7, "reason": "Grounded answer produced from retrieved context; LLM verification disabled for the fast path."}
            trace.mark("verify")

            if verification["confidence"] < _settings.MIN_CONFIDENCE or not verification["supported"]:
                result = {"answer": "I don't have enough information to answer that question confidently.", "citations": [], "confidence": verification["confidence"], "supported": verification["supported"], "reason": verification["reason"], "conflicts": []}
            else:
                citations = _chunk_citations(chunk_ids) + _fact_citations(agent_context) + _graph_citations(agent_context) + _memory_citations(agent_context)
                trace.mark("citations")
                result = {"answer": answer, "citations": citations, "confidence": verification["confidence"], "supported": verification["supported"], "reason": verification["reason"], "conflicts": []}

        db = SessionLocal()
        try:
            conversation = persist_chat_turn(db, tenant_id=tenant_id, session_id=session_id, question=question, answer=result["answer"], citations=result["citations"], confidence=result["confidence"], supported=result["supported"], reason=result["reason"])
            result["conversation_id"] = str(conversation.id)
        except ConversationScopeError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.warning(f"Chat answer returned without durable conversation persistence: {exc}")
            db.close()
            return result
        else:
            # Best-effort structured summary + outbox event so FerretDB/graph memory
            # actually gets refreshed from normal chat use, not only from the
            # dedicated /knowledge/conversations/turns path. This reuses the existing
            # summarize_conversation() outbox wiring rather than duplicating it.
            # Follow-up (explicitly out of scope here): ChatRequest has no
            # customer_id/lead_id, so this conversation is not yet linked to a
            # specific customer/lead subject the way persist_structured_turn's
            # callers can be — only the rolling free-text summary path is triggered.
            try:
                await summarize_conversation(tenant_id=tenant_id, conversation_id=conversation.id)
            except Exception as exc:
                logger.warning(f"Structured conversation summary/outbox sync skipped: {exc}")
        finally:
            db.close()
        log_db = SessionLocal()
        try:
            log_db.add(RetrievalLog(
                tenant_id=tenant_id,
                query=question,
                results=_json_safe([{"citation": citation} for citation in result.get("citations", [])]),
                scores=_json_safe([{
                    "confidence": result.get("confidence"),
                    "supported": result.get("supported"),
                    "reason": result.get("reason"),
                    "conflicts": len(result.get("conflicts") or []),
                }]),
                latency_ms=trace.elapsed_ms(),
            ))
            log_db.commit()
        except Exception as exc:
            log_db.rollback()
            logger.warning(f"Retrieval observability persistence skipped: {exc}")
        finally:
            log_db.close()
        return result
    finally:
        trace.emit()
