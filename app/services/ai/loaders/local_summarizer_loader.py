"""Local Summarizer Loader - SmolLM2-360M for text summarization.

Uses transformers AutoModelForCausalLM for local inference.
"""
from typing import Dict, Any, Optional
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader
from app.services.ai.runtime.results import SummaryResult

_settings = get_settings()


class LocalSummarizerLoader(BaseLocalLoader):
    """Local summarizer using SmolLM2-360M-Instruct.
    
    Loads model from AI_MODELS/llms/smollm2-360m
    """

    def __init__(self, model_name: str = "smollm2-360m"):
        """Initialize local summarizer loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "llms" / model_name

    async def load(self) -> None:
        """Load SmolLM2-360M summarizer model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local summarizer model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForCausalLM

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info("Loading SmolLM2-360M model...")
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local summarizer loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local summarizer: {e}")
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
        logger.info("Local summarizer unloaded")

    async def summarize(
        self,
        text: str,
        max_new_tokens: int = 128,
        min_new_tokens: int = 10,
        **kwargs,
    ) -> str:
        """Summarize text.

        Args:
            text: Text to summarize
            max_new_tokens: Maximum summary length in tokens
            min_new_tokens: Minimum summary length in tokens
            **kwargs: Additional parameters

        Returns:
            Summarized text
        """
        await self.ensure_loaded()

        try:
            import torch

            # Prepare prompt
            prompt = f"Summarize the following text:\n\n{text}\n\nSummary:"

            # Tokenize
            inputs = self._tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=1024,
            ).to(self._model.device)

            # Generate summary with fixed config to prevent repetition
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    min_new_tokens=min_new_tokens,
                    repetition_penalty=1.3,
                    no_repeat_ngram_size=4,
                    temperature=0.7,
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )

            # Decode
            summary = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            logger.debug(f"Generated summary of {len(summary)} characters")
            return SummaryResult(
                summary=summary.strip(),
                original_length=len(text),
                summary_length=len(summary),
                compression_ratio=len(summary) / len(text) if len(text) > 0 else 0.0,
                model=self.model_name
            )

        except Exception as e:
            logger.error(f"Local summarization failed: {e}")
            raise

    async def infer(self, text: str, **kwargs) -> Any:
        """Alias for summarize."""
        return await self.summarize(text, **kwargs)
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input."""
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        try:
            import time
            start = time.perf_counter()
            await self.summarize("test text for summarization")
            elapsed = time.perf_counter() - start
            return {"status": "ok", "time_s": elapsed, "model": self.model_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health."""
        if not self._loaded:
            return {"status": "not_loaded", "model": self.model_name, "loaded": False}
        try:
            await self.summarize("health check")
            return {"status": "healthy", "model": self.model_name, "loaded": True, "device": "cuda" if self._check_cuda() else "cpu"}
        except Exception as e:
            return {"status": "unhealthy", "model": self.model_name, "loaded": True, "error": str(e)}
    
    def _check_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False