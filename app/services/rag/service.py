"""RagService â€” orchestrates the full corrective RAG pipeline.

Flow:
  query â†’ classify (2-axis) â†’ cache check (embed then hash-lookup) â†’
    retrieve + correct â†’ route model â†’ generate â†’ cache write

  ingest â†’ embed â†’ upsert (dense + sparse) to Qdrant

Logs mode + correction path per query. Exposes routing stats.
"""

import time
from typing import Any
from collections import Counter

from loguru import logger

from app.services.rag.repository import get_rag_repository
from app.services.rag.cache import get_semantic_cache
from app.services.rag.classifier import (
    get_query_classifier,
    RoutingMode,
    QueryClass,
)
from app.services.rag.corrector import (
    CorrectiveLoop,
    INSUFFICIENT_RESPONSE,
    FailureType,
)
from app.services.rag.model_router import get_model_router, ModelBackend
from app.services.rag.embeddings.local import embed_query
from app.services.rag.llm.generator import generate_answer, generate_answer_streamed
from app.services.rag.llm.intent_router import resolve_mode, IntentMode
from app.config.settings import get_settings
from app.analysis.pipelines.language_service import LanguageService
from app.services.ai.gateway import get_ai_gateway

_settings = get_settings()


class RagService:
    """Orchestrator for the corrective RAG pipeline.

    Routes every query through a 2-axis classifier (needs_retrieval Ã—
    needs_reasoning) that decides the mode before any model call.
    Tracks mode distribution and correction paths for observability.
    """

    def __init__(self) -> None:
        self._repo = get_rag_repository()
        self._cache = get_semantic_cache()
        self._classifier = get_query_classifier()
        self._corrector = CorrectiveLoop()
        self._router = get_model_router()

        self._mode_counts: Counter = Counter()
        self._correction_paths: Counter = Counter()
        self._failure_type_counts: Counter = Counter()

    # â”€â”€ Query Pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def query(
        self,
        question: str,
        tenant_id: str = "",
        stream: bool = False,
    ) -> dict[str, Any]:
        """Execute the full corrective RAG pipeline.

        Returns:
            dict with keys: answer, sources, cache_hit, model_backend,
                            gave_up, latency_ms, classification,
                            mode, correction_path, failure_type, retries
        """
        start = time.perf_counter()
        stage_timings: dict[str, float] = {}

        # Step 0: Detect language & translate non-English queries to English before
        # classification + retrieval (keep original for answer generation)
        t_trans = time.perf_counter()
        original_language = LanguageService.detect(question)
        en_question = question
        if original_language != "en":
            gateway = get_ai_gateway()
            try:
                translation = await gateway.generate(
                    prompt=question,
                    system_prompt="Translate this text to English, preserving intent. Output only the translation, no explanation.",
                    model_name="qwen2.5-0.5b",
                    max_tokens=256,
                    temperature=0.05,
                )
                en_question = (translation or "").strip() or question
                logger.info("Translated query from {}: original={} translated={}", original_language, question[:80], en_question[:80])
            except Exception as exc:
                logger.warning("Query translation failed (falling back to original): {}", exc)
        stage_timings["translation_ms"] = round((time.perf_counter() - t_trans) * 1000, 1)

        # Step 1: Classify (2-axis) â€” use translated query
        t0 = time.perf_counter()
        classification = self._classifier.classify(en_question)
        stage_timings["classify_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._mode_counts[classification.mode.value] += 1

        if classification.query_class == QueryClass.OUT_OF_SCOPE:
            return {
                "answer": (
                    "I can't help with that request. "
                    "Please ask a question related to your business or knowledge base."
                ),
                "sources": [],
                "cache_hit": False,
                "model_backend": "none",
                "mode": classification.mode.value,
                "gave_up": True,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "stage_timings_ms": stage_timings,
                "classification": classification.reason,
            }

        # Step 2: Embed query for cache lookup (skip if no retrieval needed)
        t0 = time.perf_counter()
        if classification.needs_retrieval:
            query_embedding = await embed_query(en_question)
        else:
            query_embedding = []
        stage_timings["embed_query_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # Step 3: Check semantic cache (only for retrieval modes)
        cached = None
        if query_embedding:
            cached = self._cache.lookup(query_embedding, tenant_id)
        if cached is not None:
            return {
                "answer": cached["answer"],
                "sources": cached["sources"],
                "cache_hit": True,
                "model_backend": "cache",
                "mode": classification.mode.value,
                "gave_up": False,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "stage_timings_ms": stage_timings,
                "classification": classification.reason,
            }

        # Step 4: Retrieve + correct (skip for REASON_ONLY)
        chunks = []
        corrected_result = None

        if classification.needs_retrieval:
            top_k = classification.top_k or _settings.TOP_K_RETRIEVAL

            async def retrieve_fn(q: str, top_k: int = top_k, tenant_id: str = "") -> list[dict]:
                q_emb = await embed_query(q)
                return self._repo.hybrid_search(
                    dense_vector=q_emb,
                    sparse_indices=[],
                    sparse_values=[],
                    tenant_id=tenant_id,
                    top_k=top_k,
                )

            t1 = time.perf_counter()
            corrected_result = await self._corrector.execute(
                query=en_question,
                retrieve_fn=retrieve_fn,
                top_k=top_k,
                tenant_id=tenant_id,
            )
            stage_timings["qdrant_search_ms"] = round((time.perf_counter() - t1) * 1000, 1)

            # Track correction path
            corr_path = corrected_result.get("correction_path", "none")
            self._correction_paths[corr_path] += 1
            ft = corrected_result.get("failure_type", FailureType.NONE.value)
            self._failure_type_counts[ft] += 1

            if corrected_result["gave_up"]:
                logger.info(
                    "RAG retrieval empty; using general-answer fallback: mode={} correction_path={} failure_type={} retries={}",
                    classification.mode.value, corr_path, ft,
                    corrected_result.get("retries", 0),
                )
                t_gen = time.perf_counter()
                decision = self._router.select_model()
                answer = await generate_answer(
                    question=question,
                    context="",
                    mode=IntentMode.GENERAL_KNOWLEDGE,
                    language=original_language,
                    max_tokens=180,
                    model_name=_settings.QUERY_MODEL,
                )
                stage_timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 1)
                elapsed = round((time.perf_counter() - start) * 1000, 1)
                stage_timings["total_ms"] = elapsed
                return {
                    "answer": answer,
                    "sources": [],
                    "cache_hit": False,
                    "model_backend": decision.backend.value,
                    "model_name": decision.model_name,
                    "mode": "general_fallback",
                    "gave_up": False,
                    "latency_ms": elapsed,
                    "stage_timings_ms": stage_timings,
                    "classification": classification.reason,
                    "corrected": corrected_result["corrected"],
                    "retries": corrected_result["retries"],
                    "failure_type": ft,
                    "correction_path": corr_path,
                }

            chunks = corrected_result["chunks"]
        else:
            corrected_result = {
                "corrected": False,
                "retries": 0,
                "failure_type": FailureType.NONE.value,
                "correction_path": "none",
            }

        # Step 5: Build context from retrieved chunks (hard token budget)
        t0 = time.perf_counter()
        char_budget = 1200  # ~800 tokens at ~4 chars/token
        context_parts = []
        sources = []
        budget_remaining = char_budget
        # Sort by relevance (score descending) so we keep the best chunks
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0) or 0, reverse=True)
        for c in sorted_chunks:
            text = c.get("text", "")
            if not text:
                continue
            text_len = len(text)
            # Always include the highest-relevance chunk (truncated if needed)
            if not context_parts and text_len > budget_remaining:
                text = text[:budget_remaining - 10]
                text_len = len(text)
            elif text_len + 2 > budget_remaining:
                continue
            context_parts.append(text)
            budget_remaining -= text_len + 2
            sources.append({
                "chunk_id": c.get("chunk_id"),
                "score": c.get("score", 0),
                "page": c.get("page"),
                "heading": c.get("heading"),
                "document_id": c.get("document_id"),
            })
            if budget_remaining <= 100:
                break

        context = "\n\n".join(context_parts)
        stage_timings["context_build_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # Step 6: Map 2-axis mode to IntentMode for generator
        intent_mode = resolve_mode(classification)

        # Step 7: Route model and generate
        t_gen = time.perf_counter()
        decision = self._router.select_model()

        if classification.mode == RoutingMode.REASON_ONLY:
            answer = await generate_answer(
                question=question,
                context="",
                mode=intent_mode,
                language=original_language,
            )
        else:
            answer = await generate_answer(
                question=question,
                context=context,
                mode=intent_mode,
                language=original_language,
            )
        stage_timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 1)

        # Step 8: Cache the response (only for non-corrected retrieval modes)
        if (
            query_embedding
            and answer
            and not corrected_result["corrected"]
            and not answer.startswith("I don't have enough")
        ):
            self._cache.store(query_embedding, answer, sources, tenant_id)

        elapsed = round((time.perf_counter() - start) * 1000, 1)
        stage_timings["total_ms"] = elapsed
        logger.info(
            "RAG query complete: mode={} corrected={} retries={} "
            "failure_type={} correction_path={} backend={} "
            "classify={}ms embed={}ms search={}ms context={}ms total={}ms",
            classification.mode.value,
            corrected_result["corrected"],
            corrected_result["retries"],
            corrected_result.get("failure_type", "none"),
            corrected_result.get("correction_path", "none"),
            decision.backend.value,
            stage_timings.get("classify_ms", 0),
            stage_timings.get("embed_query_ms", 0),
            stage_timings.get("qdrant_search_ms", 0),
            stage_timings.get("context_build_ms", 0),
            elapsed,
        )

        return {
            "answer": answer,
            "sources": sources,
            "cache_hit": False,
            "model_backend": decision.backend.value,
            "model_name": decision.model_name,
            "mode": classification.mode.value,
            "gave_up": False,
            "latency_ms": elapsed,
            "stage_timings_ms": stage_timings,
            "classification": classification.reason,
            "corrected": corrected_result["corrected"],
            "retries": corrected_result["retries"],
            "failure_type": corrected_result.get("failure_type", FailureType.NONE.value),
            "correction_path": corrected_result.get("correction_path", "none"),
        }

    async def stream_answer(
        self,
        question: str,
        tenant_id: str = "",
        meta: dict | None = None,
        response_style: str | None = None,
    ):
        """Async generator: runs the full RAG pipeline, yields answer tokens.

        Populates *meta* dict (if provided) with timing & sources after
        the generator is exhausted.
        """
        start = time.perf_counter()
        stage_timings: dict[str, float] = {}

        # Step 0: Preserve the original speech transcript for retrieval.
        # The previous 0.5B "translation" model hallucinated English facts and
        # changed the search intent. Nomic embeddings can search mixed Tamil/
        # English input directly, including English technical terms from STT.
        t_trans = time.perf_counter()
        original_language = LanguageService.detect(question)
        en_question = question
        if original_language != "en":
            logger.info("RAG multilingual retrieval uses original transcript; translation skipped")
        stage_timings["translation_ms"] = round((time.perf_counter() - t_trans) * 1000, 1)

        # Step 1: Classify (2-axis)
        t0 = time.perf_counter()
        classification = self._classifier.classify(en_question)
        stage_timings["classify_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._mode_counts[classification.mode.value] += 1

        if classification.query_class == QueryClass.OUT_OF_SCOPE:
            answer = (
                "I can't help with that request. "
                "Please ask a question related to your business or knowledge base."
            )
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            if meta is not None:
                meta["stage_timings_ms"] = stage_timings
                meta["latency_ms"] = elapsed
                meta["sources"] = []
            yield answer
            return

        # Step 2: Embed query
        t0 = time.perf_counter()
        if classification.needs_retrieval:
            query_embedding = await embed_query(en_question)
        else:
            query_embedding = []
        stage_timings["embed_query_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # Step 3: Check semantic cache
        cached = None
        if query_embedding:
            cached = self._cache.lookup(query_embedding, tenant_id)
        if cached is not None:
            answer = cached["answer"]
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            if meta is not None:
                meta["stage_timings_ms"] = stage_timings
                meta["latency_ms"] = elapsed
                meta["sources"] = cached["sources"]
            yield answer
            return

        # Step 4: Retrieve + correct
        chunks = []
        corrected_result = None

        if classification.needs_retrieval:
            top_k = classification.top_k or _settings.TOP_K_RETRIEVAL

            async def retrieve_fn(q: str, top_k: int = top_k, tenant_id: str = "") -> list[dict]:
                q_emb = await embed_query(q)
                return self._repo.hybrid_search(
                    dense_vector=q_emb, sparse_indices=[], sparse_values=[],
                    tenant_id=tenant_id, top_k=top_k,
                )

            t1 = time.perf_counter()
            corrected_result = await self._corrector.execute(
                query=en_question, retrieve_fn=retrieve_fn,
                top_k=top_k, tenant_id=tenant_id,
            )
            stage_timings["qdrant_search_ms"] = round((time.perf_counter() - t1) * 1000, 1)

            corr_path = corrected_result.get("correction_path", "none")
            self._correction_paths[corr_path] += 1
            ft = corrected_result.get("failure_type", FailureType.NONE.value)
            self._failure_type_counts[ft] += 1

            if corrected_result["gave_up"]:
                logger.info("RAG retrieval empty; using general-answer fallback (stream): mode={} path={} failure={} retries={}",
                            classification.mode.value, corr_path, ft,
                            corrected_result.get("retries", 0))
                t_gen = time.perf_counter()
                token_count = 0
                answer_gen = generate_answer_streamed(
                    question=question,
                    context="",
                    mode=IntentMode.GENERAL_KNOWLEDGE,
                    language=original_language,
                    response_style=response_style,
                    max_tokens=180,
                    model_name=_settings.QUERY_MODEL,
                )
                async for token in answer_gen:
                    token_count += 1
                    yield token
                stage_timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 1)
                elapsed = round((time.perf_counter() - start) * 1000, 1)
                stage_timings["total_ms"] = elapsed
                if meta is not None:
                    meta["stage_timings_ms"] = stage_timings
                    meta["latency_ms"] = elapsed
                    meta["sources"] = []
                    meta["mode"] = "general_fallback"
                return

            chunks = corrected_result["chunks"]
        else:
            corrected_result = {
                "corrected": False, "retries": 0,
                "failure_type": FailureType.NONE.value, "correction_path": "none",
            }

        # Step 5: Build context (same token budget as query())
        t0 = time.perf_counter()
        char_budget = 1200
        context_parts = []
        sources = []
        budget_remaining = char_budget
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0) or 0, reverse=True)
        for c in sorted_chunks:
            text = c.get("text", "")
            if not text:
                continue
            text_len = len(text)
            if not context_parts and text_len > budget_remaining:
                text = text[:budget_remaining - 10]
                text_len = len(text)
            elif text_len + 2 > budget_remaining:
                continue
            context_parts.append(text)
            budget_remaining -= text_len + 2
            sources.append({
                "chunk_id": c.get("chunk_id"), "score": c.get("score", 0),
                "page": c.get("page"), "heading": c.get("heading"),
                "document_id": c.get("document_id"),
            })
            if budget_remaining <= 100:
                break
        context = "\n\n".join(context_parts)
        stage_timings["context_build_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # Step 6/7: Speak a concise, source-grounded answer.  Do not use the
        # reasoning template here: it encourages FACT/INFERENCE labels and long,
        # repetitive answers that are unsuitable for a live call.
        intent_mode = IntentMode.COMPANY_KNOWLEDGE
        t_gen = time.perf_counter()
        answer_gen = generate_answer_streamed(
            question=question,
            context=context,
            mode=intent_mode,
            language=original_language,
            response_style=response_style,
            max_tokens=180,
            temperature=0.05,
            model_name=_settings.GENERATOR_MODEL,
        )

        token_count = 0
        async for token in answer_gen:
            token_count += 1
            yield token

        stage_timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 1)

        elapsed = round((time.perf_counter() - start) * 1000, 1)
        stage_timings["total_ms"] = elapsed
        logger.info(
            "RAG stream complete (tokens={}): mode={} classify={}ms embed={}ms "
            "search={}ms context={}ms gen={}ms total={}ms",
            token_count, classification.mode.value,
            stage_timings.get("classify_ms", 0),
            stage_timings.get("embed_query_ms", 0),
            stage_timings.get("qdrant_search_ms", 0),
            stage_timings.get("context_build_ms", 0),
            stage_timings.get("generation_ms", 0),
            elapsed,
        )

        if meta is not None:
            meta["stage_timings_ms"] = stage_timings
            meta["latency_ms"] = elapsed
            meta["sources"] = sources
            meta["mode"] = classification.mode.value

    # â”€â”€ Ingest Pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def ingest(
        self,
        chunks: list[dict[str, Any]],
        tenant_id: str,
    ) -> dict[str, Any]:
        """Index chunks into Qdrant with dense + sparse vectors."""
        if not chunks:
            return {"indexed": 0, "tenant_id": tenant_id}

        texts = [c.get("text") or c.get("content", "") for c in chunks]
        from app.services.rag.embeddings.local import embed_texts
        dense_vectors = await embed_texts(texts)

        payloads = []
        for c in chunks:
            p = dict(c)
            p["tenant_id"] = tenant_id
            p.pop("vector", None)
            payloads.append(p)

        count = self._repo.upsert_chunks(
            chunk_ids=[c["id"] for c in chunks],
            dense_vectors=dense_vectors,
            payloads=payloads,
        )

        logger.info("Ingested {} chunks for tenant={}", count, tenant_id)
        return {"indexed": count, "tenant_id": tenant_id}

    # â”€â”€ Cache + Routing Stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def cache_stats(self) -> dict[str, Any]:
        stats = self._cache.stats()
        routing_log = self._router.get_routing_log()
        total_local = sum(1 for r in routing_log if r["backend"] == ModelBackend.LOCAL_GGUF.value)
        return {
            "cache": stats,
            "routing": {
                "total_requests": len(routing_log),
                "local_gguf": total_local,
                "mode_distribution": dict(self._mode_counts),
                "correction_paths": dict(self._correction_paths),
                "failure_types": dict(self._failure_type_counts),
            },
        }


_service: RagService | None = None


def get_rag_service() -> RagService:
    global _service
    if _service is None:
        _service = RagService()
    return _service

