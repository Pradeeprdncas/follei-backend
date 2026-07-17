"""Local Classifier Loader - ModernBERT-base for intent classification.

Uses transformers AutoModelForSequenceClassification for local inference.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader

_settings = get_settings()


class LocalClassifierLoader(BaseLocalLoader):
    """Local intent classifier using ModernBERT-base.

    Loads model from AI_MODELS/classifiers/ModernBERT-base
    """

    def __init__(self, model_name: str = "ModernBERT-base"):
        """Initialize local classifier loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "classifiers" / model_name

        # Define intents matching the existing IntentClassifier
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
            "tool_execution",
            "database_query",
            "crm_operation",
            "agent_task",
        ]

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
        """Load ModernBERT classifier model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local classifier model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info(f"Loading {self.model_name} model...")
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local classifier loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local classifier: {e}")
            raise

    async def unload(self) -> None:
        """Unload model."""
        if self._model:
            del self._model
            self._model = None
        if self._tokenizer:
            del self._tokenizer
            self._tokenizer = None
        self._loaded = False
        logger.info("Local classifier unloaded")

    async def infer(
        self,
        text: str,
        top_k: int = 3,
        **kwargs,
    ) -> Dict[str, Any]:
        """Classify intent of text.

        Args:
            text: Input text to classify
            top_k: Number of top intents to return
            **kwargs: Additional parameters

        Returns:
            Classification result with intents, confidence, and explanation
        """
        await self.ensure_loaded()

        try:
            import torch

            # Tokenize
            inputs = self._tokenizer(
                text,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self._model.device)

            # Inference
            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits

            # Softmax to get probabilities
            probs = torch.softmax(logits, dim=-1)[0]

            # Get top-k intents
            top_probs, top_indices = torch.topk(
                probs, min(top_k, len(self._intents))
            )

            # Build results
            intents = []
            for prob_val, idx in zip(top_probs, top_indices):
                intent_name = self._intents[idx.item()]
                intents.append(
                    {
                        "intent": intent_name,
                        "confidence": float(prob_val.item()),
                        "description": self._intent_descriptions.get(
                            intent_name, ""
                        ),
                    }
                )

            # Primary intent
            primary_intent = intents[0] if intents else {
                "intent": "general_query",
                "confidence": 0.0,
                "description": "",
            }

            # Check if confidence is above threshold
            confidence_threshold = 0.3
            is_unknown = primary_intent["confidence"] < confidence_threshold

            result = {
                "primary_intent": primary_intent["intent"],
                "confidence": primary_intent["confidence"],
                "intents": intents,
                "is_unknown": is_unknown,
                "explanation": self._generate_explanation(intents, text),
            }

            logger.debug(
                f"Classifier result: intent={result['primary_intent']}, "
                f"confidence={result['confidence']:.3f}"
            )
            return result

        except Exception as e:
            logger.error(f"Local classification failed: {e}")
            return self._default_result(text)

    def _generate_explanation(
        self, intents: List[Dict], text: str
    ) -> str:
        """Generate human-readable explanation."""
        if not intents:
            return "Unable to determine intent"

        primary = intents[0]

        if primary["confidence"] < 0.3:
            return (
                f"Low confidence ({primary['confidence']:.2f}). Intent unclear."
            )

        explanation = (
            f"Classified as '{primary['intent']}' with "
            f"{primary['confidence']:.1%} confidence. "
        )
        explanation += f"{primary['description']}. "

        if len(intents) > 1:
            secondary = intents[1]
            explanation += (
                f"Secondary: '{secondary['intent']}' "
                f"({secondary['confidence']:.1%})."
            )

        return explanation

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
        }

    async def classify(self, text: str) -> Any:
        """Classify intent of text, returning a standardized ClassificationResult."""
        res_dict = await self.infer(text, top_k=1)
        from app.services.ai.runtime.results import ClassificationResult
        return ClassificationResult(
            primary_intent=res_dict["primary_intent"],
            confidence=res_dict["confidence"],
            model=self.model_name
        )
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input.
        
        Returns:
            Dict with warmup results
        """
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        
        try:
            import time
            start = time.perf_counter()
            
            # Tiny warmup inference
            await self.classify("test")
            
            elapsed = time.perf_counter() - start
            logger.debug(f"Classifier warmup: {elapsed:.3f}s")
            
            return {
                "status": "ok",
                "time_s": elapsed,
                "model": self.model_name,
            }
        except Exception as e:
            logger.error(f"Classifier warmup failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health.
        
        Returns:
            Dict with health status
        """
        if not self._loaded:
            return {
                "status": "not_loaded",
                "model": self.model_name,
                "loaded": False,
            }
        
        try:
            # Verify model is responsive
            await self.classify("health check")
            
            return {
                "status": "healthy",
                "model": self.model_name,
                "loaded": True,
                "device": "cuda" if self._check_cuda() else "cpu",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model_name,
                "loaded": True,
                "error": str(e),
            }
    
    def _check_cuda(self) -> bool:
        """Check if CUDA is available.
        
        Returns:
            True if CUDA is available
        """
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
