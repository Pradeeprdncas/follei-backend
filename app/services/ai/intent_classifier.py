"""Intent Classifier using ModernBERT via ModelManager.

Routes through ModelManager → LocalClassifierLoader instead of direct model loading.
Provides confidence scores, multi-intent support, and explanations.
"""
from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class IntentClassifier:
    """Intent classification using ModernBERT via ModelManager.

    All model loading goes through ModelManager → LocalClassifierLoader.
    Never loads models directly - always uses the AI Router's ModelManager.

    Features:
    - High accuracy intent classification
    - Confidence scores
    - Top-k intents
    - Multi-intent support
    - Unknown intent detection
    - Intent explanations
    - Caching
    - <30ms latency target
    """

    def __init__(self):
        """Initialize intent classifier."""
        self._model_manager = None
        self._loaded = False
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour

        # Define intents
        self._intents = [
            "general_query",
            "support_request",
            "sales_inquiry",
            "lead_qualification",
            "complaint",
            "feedback",
            "billing_question",
            "technical_issue",
            "feature_request",
            "tool_execution",  # MCP tools
            "database_query",
            "crm_operation",
            "agent_task",
        ]

        # Intent descriptions for explanations
        self._intent_descriptions = {
            "general_query": "General information request",
            "support_request": "Technical support or help needed",
            "sales_inquiry": "Product or pricing questions",
            "lead_qualification": "Interest in purchasing or demo",
            "complaint": "Negative feedback or issues",
            "feedback": "Suggestions or positive feedback",
            "billing_question": "Invoices, payments, subscriptions",
            "technical_issue": "Bugs, errors, or technical problems",
            "feature_request": "New feature suggestions",
            "tool_execution": "Request to execute external tools (email, calendar, etc.)",
            "database_query": "Request to query database",
            "crm_operation": "Request to perform CRM operations",
            "agent_task": "Request for multi-step automated task",
        }

    async def load(self) -> None:
        """Load the model via ModelManager."""
        if self._loaded:
            return

        try:
            logger.info("Loading intent classifier via ModelManager...")

            # Use ModelManager to get the classifier model
            from app.services.ai.model_manager import get_model_manager

            self._model_manager = get_model_manager()
            model_info = await self._model_manager.get_model(
                "classifier", _settings.INTENT_MODEL
            )

            self._loaded = True
            logger.info("Intent classifier loaded successfully via ModelManager")

        except Exception as e:
            logger.error(f"Failed to load intent classifier: {e}")
            raise

    async def unload(self) -> None:
        """Unload model via ModelManager."""
        if self._model_manager:
            try:
                await self._model_manager.unload_model(
                    "classifier", _settings.INTENT_MODEL
                )
            except Exception as e:
                logger.warning(f"Failed to unload classifier: {e}")
        self._loaded = False
        self._cache.clear()
        logger.info("Intent classifier unloaded")

    async def classify(
        self,
        text: str,
        top_k: int = 3,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Classify intent of text using ModelManager.

        Args:
            text: Input text
            top_k: Number of top intents to return
            use_cache: Whether to use cache

        Returns:
            Classification result with intents, confidence, and explanation
        """
        # Check cache
        if use_cache:
            cache_key = f"{text}:{top_k}"
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug("Intent classification cache hit")
                return cached

        try:
            # Always load through ModelManager
            if not self._loaded:
                await self.load()

            # Get the model from ModelManager's registry
            model_info = await self._model_manager.get_model(
                "classifier", _settings.INTENT_MODEL
            )
            loader = model_info["loader"]

            # Run inference through the loader
            result = await loader.infer(text=text, top_k=top_k)

            # Cache result
            if use_cache:
                self._add_to_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return self._default_result(text)

    def _default_result(self, text: str) -> Dict[str, Any]:
        """Return default result on failure."""
        return {
            "primary_intent": "general_query",
            "confidence": 0.5,
            "intents": [
                {
                    "intent": "general_query",
                    "confidence": 0.5,
                    "description": "General information request",
                }
            ],
            "is_unknown": False,
            "explanation": "Classification failed, defaulting to general query",
            "latency_ms": 0,
        }

    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get item from cache."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            import time

            if time.time() - timestamp < self._cache_ttl:
                return result
            else:
                del self._cache[key]
        return None

    def _add_to_cache(self, key: str, value: Dict[str, Any]) -> None:
        """Add item to cache."""
        import time

        self._cache[key] = (value, time.time())

        # Limit cache size
        if len(self._cache) > 1000:
            sorted_keys = sorted(self._cache.items(), key=lambda x: x[1][1])
            for key, _ in sorted_keys[:100]:
                del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """Get classifier statistics."""
        return {
            "loaded": self._loaded,
            "model": _settings.INTENT_MODEL,
            "loading_method": "ModelManager",
            "cache_size": len(self._cache),
            "intents": len(self._intents),
        }


# Singleton instance
_intent_classifier = None


def get_intent_classifier() -> IntentClassifier:
    """Get or create singleton intent classifier."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier