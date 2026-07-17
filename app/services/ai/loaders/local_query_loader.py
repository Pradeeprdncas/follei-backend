"""Local Query Optimizer Loader - Qwen2.5-0.5B for query rewriting.

Uses transformers AutoModelForCausalLM for local inference.
"""
from typing import Dict, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader

_settings = get_settings()


class LocalQueryOptimizerLoader(BaseLocalLoader):
    """Local query optimizer/rewriter using Qwen2.5-0.5B-Instruct.
    
    Loads model from AI_MODELS/llms/qwen2.5-0.5b
    """

    def __init__(self, model_name: str = "qwen2.5-0.5b"):
        """Initialize local query optimizer loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "llms" / model_name

    async def load(self) -> None:
        """Load Qwen2.5-0.5B query optimizer model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local query optimizer model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForCausalLM

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info("Loading Qwen2.5-0.5B model...")
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local query optimizer loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local query optimizer: {e}")
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
        logger.info("Local query optimizer unloaded")

    async def rewrite_query(self, query: str, context: str = "") -> Any:
        """Rewrite/optimize query for better retrieval.

        Args:
            query: Original query
            context: Additional context

        Returns:
            QueryRewriteResult object
        """
        await self.ensure_loaded()

        try:
            import torch
            import re
            from app.services.ai.runtime.results import QueryRewriteResult

            # Prepare prompt — one-line instruction forces short output
            prompt = (
                f"Rewrite as a short search query (max 8 words, no explanation):\n"
                f"Input: {query}\n"
                f"Output:"
            )

            # Build stop-token ids: newline + EOS both terminate the query
            stop_ids = [self._tokenizer.eos_token_id]
            for tok in ["\n", "\r\n"]:
                try:
                    ids = self._tokenizer.encode(tok, add_special_tokens=False)
                    stop_ids.extend(ids)
                except Exception:
                    pass
            stop_ids = list(set(filter(None, stop_ids)))

            # Tokenize
            inputs = self._tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=256,
            ).to(self._model.device)

            # Generate — hard cap: 30 tokens is enough for any search query
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=30,
                    temperature=0.1,
                    top_p=0.9,
                    do_sample=False,  # greedy — deterministic, no hallucination
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=stop_ids,
                )

            # Decode
            rewritten_raw = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            # Robust cleanup
            rewritten = rewritten_raw.strip()
            # Strip markdown block wrappers
            rewritten = re.sub(r"```(markdown|json)?", "", rewritten)
            rewritten = rewritten.replace("```", "")
            
            # Check if it looks like JSON
            rewritten_stripped = rewritten.strip()
            if rewritten_stripped.startswith("{") and rewritten_stripped.endswith("}"):
                try:
                    import json
                    data = json.loads(rewritten_stripped)
                    # Try common keys
                    for key in ["optimized_search_query", "rewritten_query", "query", "text"]:
                        if key in data:
                            rewritten = str(data[key])
                            break
                except Exception:
                    pass

            # Remove quotes
            rewritten = rewritten.replace('"', '').replace("'", "")
            
            # Strip common prefix labels (case-insensitive)
            prefixes = [
                r"^rewritten query\s*:\s*",
                r"^optimized query\s*:\s*",
                r"^search query\s*:\s*",
                r"^query\s*:\s*",
                r"^output\s*:\s*"
            ]
            for p in prefixes:
                rewritten = re.sub(p, "", rewritten, flags=re.IGNORECASE)
                
            # Split by common indicators of extra text (like explanation, reasoning, notes, etc.)
            splitters = [
                "\nExplanation:", "\nReasoning:", "\nNote:", "\nWhy:",
                "\nHere is", "\nThis query", "\nI have", "\nI rewrote",
                " - Explanation", " (Explanation", " - Note", " (Note"
            ]
            for splitter in splitters:
                if splitter in rewritten:
                    rewritten = rewritten.split(splitter)[0]
                    
            # Also handle single-line versions
            rewritten = re.split(r"\s+explanation\s*:\s*", rewritten, flags=re.IGNORECASE)[0]
            rewritten = re.split(r"\s+note\s*:\s*", rewritten, flags=re.IGNORECASE)[0]
            rewritten = re.split(r"\s+reasoning\s*:\s*", rewritten, flags=re.IGNORECASE)[0]

            rewritten = rewritten.strip()
            logger.debug(f"Rewritten query: {rewritten}")
            
            return QueryRewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                model=self.model_name
            )

        except Exception as e:
            logger.error(f"Query rewriting failed: {e}")
            from app.services.ai.runtime.results import QueryRewriteResult
            return QueryRewriteResult(
                original_query=query,
                rewritten_query=query,
                model=self.model_name
            )

    async def infer(self, text: str, **kwargs) -> Any:
        """Alias for rewrite_query."""
        return await self.rewrite_query(text)
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input."""
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        try:
            import time
            start = time.perf_counter()
            await self.rewrite_query("test query")
            elapsed = time.perf_counter() - start
            return {"status": "ok", "time_s": elapsed, "model": self.model_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health."""
        if not self._loaded:
            return {"status": "not_loaded", "model": self.model_name, "loaded": False}
        try:
            await self.rewrite_query("health check")
            return {"status": "healthy", "model": self.model_name, "loaded": True, "device": "cuda" if self._check_cuda() else "cpu"}
        except Exception as e:
            return {"status": "unhealthy", "model": self.model_name, "loaded": True, "error": str(e)}
    
    def _check_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
