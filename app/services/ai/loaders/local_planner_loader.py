"""Local Planner Loader - Qwen2.5-0.5B for task planning.

Uses transformers AutoModelForCausalLM for local inference.
"""
from typing import Dict, Any
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader

_settings = get_settings()


class LocalPlannerLoader(BaseLocalLoader):
    """Local task planner using Qwen2.5-0.5B-Instruct.
    
    Loads model from AI_MODELS/llms/qwen2.5-0.5b
    """

    def __init__(self, model_name: str = "qwen2.5-0.5b"):
        """Initialize local planner loader.

        Args:
            model_name: Model name
        """
        super().__init__(model_name=model_name)
        self._model = None
        self._tokenizer = None
        self._model_path = Path(_settings.AI_MODELS) / "llms" / model_name

    async def load(self) -> None:
        """Load Qwen2.5-0.5B planner model."""
        if self._loaded:
            return

        try:
            logger.info(f"Loading local planner model: {self.model_name}")

            from transformers import AutoTokenizer, AutoModelForCausalLM

            # Load tokenizer
            model_path = self._normalize_path(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )

            # Load model
            logger.info("Loading Qwen2.5-0.5B model for planning...")
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype="auto",
            )

            self._loaded = True
            logger.info(f"Local planner loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load local planner: {e}")
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
        logger.info("Local planner unloaded")

    async def plan(
        self,
        task: str,
        context: str = "",
        max_steps: int = 5,
    ) -> Dict[str, Any]:
        """Generate execution plan for a task.

        Args:
            task: Task description
            context: Additional context
            max_steps: Maximum number of steps

        Returns:
            Execution plan with steps
        """
        await self.ensure_loaded()

        try:
            import torch

            # Prepare prompt
            prompt = f"""Create a step-by-step plan to accomplish the following task:

Task: {task}
{f"Context: {context}" if context else ""}

Provide a numbered list of steps (max {max_steps} steps):

Plan:"""

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
                    max_new_tokens=300,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True,
                    pad_token_id=self._tokenizer.eos_token_id,
                )

            # Decode
            plan_text = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            # Parse steps
            steps = []
            for line in plan_text.strip().split("\n"):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("-")):
                    steps.append(line)

            logger.debug(f"Generated plan with {len(steps)} steps")
            from app.services.ai.runtime.results import PlanResult
            return PlanResult(
                plan=steps[:max_steps],
                reasoning=plan_text.strip(),
                model=self.model_name
            )

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            from app.services.ai.runtime.results import PlanResult
            return PlanResult(
                plan=[],
                reasoning=f"Planning failed: {e}",
                model=self.model_name
            )

    async def infer(self, text: str, **kwargs) -> Any:
        """Alias for plan."""
        return await self.plan(text, **kwargs)
    
    async def warmup(self) -> Dict[str, Any]:
        """Warm up model with dummy input."""
        if not self._loaded:
            return {"status": "skipped", "reason": "model not loaded"}
        try:
            import time
            start = time.perf_counter()
            await self.plan("test task")
            elapsed = time.perf_counter() - start
            return {"status": "ok", "time_s": elapsed, "model": self.model_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health(self) -> Dict[str, Any]:
        """Check model health."""
        if not self._loaded:
            return {"status": "not_loaded", "model": self.model_name, "loaded": False}
        try:
            await self.plan("health check")
            return {"status": "healthy", "model": self.model_name, "loaded": True, "device": "cuda" if self._check_cuda() else "cpu"}
        except Exception as e:
            return {"status": "unhealthy", "model": self.model_name, "loaded": True, "error": str(e)}
    
    def _check_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
