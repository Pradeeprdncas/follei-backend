"""Local Verifier Loader - SmolLM2-360M for answer verification.

Uses transformers AutoModelForCausalLM for local inference.
"""
from typing import Dict, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader

_settings = get_settings()


class LocalVerifierLoader(BaseLocalLoader):
    """Local answer verifier using SmolLM2-360M-Instruct.
    
    Loads model from AI_MODELS/llms/smollm2-360m
    """

    def __init__(self, model_name: str = "smollm2-360m"):
        """Initialize local verifier loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "llms" / model_name

    async def load(self) -> None:
        """Load SmolLM2-360M verifier model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local verifier model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForCausalLM

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info("Loading SmolLM2-360M model for verification...")
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local verifier loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local verifier: {e}")
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
        logger.info("Local verifier unloaded")

    async def verify(
        self,
        question: str,
        answer: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """Verify if answer is correct and supported by context.

        Args:
            question: Original question
            answer: Answer to verify
            context: Supporting context (optional)

        Returns:
            Verification result with confidence and explanation
        """
        await self.ensure_loaded()

        try:
            import torch

            # Prepare prompt
            prompt = f"""Verify if the following answer is correct and supported by the context.

Question: {question}
Answer: {answer}
{f"Context: {context}" if context else ""}

Is this answer correct and supported? Answer YES or NO and explain why.

Verification:"""

            # Tokenize
            inputs = self._tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            ).to(self._model.device)

            # Generate
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=100,
                    temperature=0.3,
                    top_p=0.9,
                    do_sample=True,
                    pad_token_id=self._tokenizer.eos_token_id,
                )

            # Decode
            verification = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            from app.services.ai.runtime.results import VerificationResult

            # Parse result
            is_correct = "yes" in verification.lower()
            confidence = 0.9 if is_correct else 0.3

            logger.debug(f"Verification: correct={is_correct}, confidence={confidence}")
            return VerificationResult(
                is_correct=is_correct,
                confidence=confidence,
                explanation=verification.strip(),
                model=self.model_name
            )

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            from app.services.ai.runtime.results import VerificationResult
            return VerificationResult(
                is_correct=False,
                confidence=0.0,
                explanation=f"Verification failed: {e}",
                model=self.model_name
            )

    async def infer(self, question: str, answer: str, **kwargs) -> Any:
        """Alias for verify."""
        return await self.verify(question, answer, **kwargs)
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input."""
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        try:
            import time
            start = time.perf_counter()
            await self.verify("test", "test answer", "test context")
            elapsed = time.perf_counter() - start
            return {"status": "ok", "time_s": elapsed, "model": self.model_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health."""
        if not self._loaded:
            return {"status": "not_loaded", "model": self.model_name, "loaded": False}
        try:
            await self.verify("health", "test", "test")
            return {"status": "healthy", "model": self.model_name, "loaded": True, "device": "cuda" if self._check_cuda() else "cpu"}
        except Exception as e:
            return {"status": "unhealthy", "model": self.model_name, "loaded": True, "error": str(e)}
    
    def _check_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
