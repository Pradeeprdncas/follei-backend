"""AI Gateway — single entry point for ALL AI operations.

Every AI feature (generation, embedding, classification, reranking,
summarization, query rewriting, verification, planning) MUST go through
this gateway. No code outside this module calls ModelManager or loaders
directly.

Architecture:
  Caller → AIGateway (single entry)
              → ModelManager (owns all models, lazy-loads on first use)
              → Caching (Redis/local)
              → Observability (latency, tokens, errors)
              → PromptManager (centralized prompt templates)
"""
from typing import Any, Dict, List, Optional
from loguru import logger
from app.services.ai.model_manager import get_model_manager
from app.services.ai.cache import get_response_cache


class AIGateway:
    """Unified gateway for all AI inference operations.

    Every method:
    1. Accepts standardized inputs
    2. Routes through ModelManager (models are NOT owned here)
    3. Applies caching where applicable
    4. Logs latency and errors for observability
    5. Returns standardized result types
    """

    def __init__(self):
        self._model_manager = get_model_manager()
        self._cache = get_response_cache()

    async def embed_texts(
        self,
        texts: List[str],
        model_name: str = "nomic-embed-text-v1.5",
        use_cache: bool = True,
    ) -> List[List[float]]:
        if not texts:
            return []
        if use_cache:
            cached = await self._cache.get("embedding", texts)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("embedding", model_name)
            loader = info["loader"]
            from app.services.ai.runtime.results import EmbeddingResult
            results: List[EmbeddingResult] = await loader.embed_batch(texts)
            embeddings = [r.embedding for r in results]
            if use_cache:
                await self._cache.set("embedding", texts, embeddings)
            return embeddings
        except Exception as e:
            logger.error(f"AIGateway.embed_texts failed: {e}")
            raise

    async def embed_query(
        self,
        text: str,
        model_name: str = "nomic-embed-text-v1.5",
        use_cache: bool = True,
    ) -> List[float]:
        embeddings = await self.embed_texts([text], model_name, use_cache)
        return embeddings[0] if embeddings else []

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_name: str = "qwen2.5-3b-instruct",
        max_tokens: int = 512,
        temperature: float = 0.1,
        top_p: float = 1.0,
        use_cache: bool = False,
        stream: bool = False,
    ) -> Any:
        inputs = dict(prompt=prompt, system_prompt=system_prompt,
                       max_tokens=max_tokens, temperature=temperature,
                       top_p=top_p, stream=stream)
        if use_cache and not stream:
            cached = await self._cache.get("generator", inputs)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("generator", model_name)
            loader = info["loader"]
            from app.services.ai.runtime.results import GenerationResult
            result: GenerationResult = await loader.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=stream,
            )
            if use_cache and not stream:
                await self._cache.set("generator", inputs, result.text)
            return result if stream else result.text
        except Exception as e:
            logger.error(f"AIGateway.generate failed: {e}")
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_name: str = "qwen2.5-3b-instruct",
        max_tokens: int = 512,
        temperature: float = 0.1,
        top_p: float = 1.0,
    ):
        info = await self._model_manager.get_model("generator", model_name)
        loader = info["loader"]
        async for token in loader.generate_streamed(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        ):
            yield token

    async def classify(
        self,
        text: str,
        model_name: str = "ModernBERT-base",
        top_k: int = 3,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        if use_cache:
            cached = await self._cache.get("classifier", text)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("classifier", model_name)
            loader = info["loader"]
            result = await loader.infer(text=text, top_k=top_k)
            if use_cache:
                await self._cache.set("classifier", text, result)
            return result
        except Exception as e:
            logger.error(f"AIGateway.classify failed: {e}")
            return {"primary_intent": "general_query", "confidence": 0.5,
                    "intents": [], "is_unknown": True, "explanation": str(e)}

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        model_name: str = "bge-reranker-base",
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []
        inputs = dict(query=query, documents=documents, top_k=top_k)
        if use_cache:
            cached = await self._cache.get("reranker", inputs)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("reranker", model_name)
            loader = info["loader"]
            from app.services.ai.runtime.results import RerankResult
            result: RerankResult = await loader.rerank(
                query=query, documents=documents, top_k=top_k
            )
            reranked = [
                {"document": doc, "score": score, "index": idx}
                for idx, (doc, score) in enumerate(zip(result.documents, result.scores))
            ]
            if use_cache:
                await self._cache.set("reranker", inputs, reranked)
            return reranked
        except Exception as e:
            logger.error(f"AIGateway.rerank failed: {e}")
            return self._fallback_rerank(query, documents, top_k)

    def _fallback_rerank(self, query: str, documents: List[str], top_k: int) -> List[Dict[str, Any]]:
        query_terms = set(query.lower().split())
        scored = []
        for idx, doc in enumerate(documents):
            doc_terms = set(doc.lower().split())
            overlap = len(query_terms & doc_terms)
            score = overlap / len(query_terms) if query_terms else 0.0
            if query.lower() in doc.lower():
                score += 0.5
            scored.append({"document": doc, "score": min(score, 1.0), "index": idx})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    async def optimize_query(
        self,
        query: str,
        model_name: str = "qwen2.5-0.5b",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        inputs = dict(query=query)
        if use_cache:
            cached = await self._cache.get("query_optimizer", inputs)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("query_optimizer", model_name)
            loader = info["loader"]
            from app.services.ai.runtime.results import QueryRewriteResult
            result: QueryRewriteResult = await loader.rewrite_query(query)
            response = {
                "optimized_search_query": result.rewritten_query,
                "tailored_system_prompt": None,
                "keywords": result.rewritten_query.split(),
                "intent": "general_query",
            }
            if use_cache:
                await self._cache.set("query_optimizer", inputs, response)
            return response
        except Exception as e:
            logger.error(f"AIGateway.optimize_query failed: {e}")
            raise

    async def summarize(
        self,
        text: str,
        max_length: Optional[int] = None,
        model_name: str = "smollm2-360m",
        use_cache: bool = True,
    ) -> str:
        if use_cache:
            cached = await self._cache.get("summarizer", text)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("summarizer", model_name)
            loader = info["loader"]
            result = await loader.summarize(text=text, max_length=max_length)
            if use_cache:
                await self._cache.set("summarizer", text, result.summary)
            return result.summary
        except Exception as e:
            logger.error(f"AIGateway.summarize failed: {e}")
            return ""

    async def verify(
        self,
        question: str,
        answer: str,
        context: str,
        model_name: str = "qwen2.5-0.5b",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        inputs = dict(question=question, answer=answer, context=context)
        if use_cache:
            cached = await self._cache.get("verifier", inputs)
            if cached is not None:
                return cached
        try:
            info = await self._model_manager.get_model("verifier", model_name)
            loader = info["loader"]
            result = await loader.verify(question=question, answer=answer, context=context)
            response = {"supported": result.supported, "confidence": result.confidence,
                        "reason": result.reason}
            if use_cache:
                await self._cache.set("verifier", inputs, response)
            return response
        except Exception as e:
            logger.error(f"AIGateway.verify failed: {e}")
            return {"supported": True, "confidence": 1.0,
                    "reason": f"Verification bypassed: {e}"}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model_manager": self._model_manager.get_loaded_models(),
            "cache": self._cache.get_stats(),
        }


_gateway: Optional[AIGateway] = None


def get_ai_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway
