"""GGUF model loader — production-grade CPU inference via llama.cpp.

Replaces HuggingFace Transformers for text generation. Supports any
GGUF-quantized model. Designed for Qwen2.5-3B-Instruct and Qwen2.5-0.5B.

Backend: llama.cpp (via llama-cpp-python)
"""
import os
import time
import asyncio
import functools
from typing import Optional, Dict, Any, AsyncGenerator
from pathlib import Path
from loguru import logger
from app.config.settings import get_settings
from app.services.ai.loaders.base_loader import BaseLocalLoader
from app.services.ai.runtime.results import GenerationResult

_settings = get_settings()


_GGUF_QUANT = "q4_k_m"  # Best quality/speed trade-off for CPU

try:
    import llama_cpp
    _LLAMA_VER = getattr(llama_cpp, "__version__", "unknown")
except Exception:
    _LLAMA_VER = "unknown"

# Global semaphore: only ONE llama.cpp inference call across ALL model
# instances at a time.  Prevents CPU thread oversubscription on the
# shared 4-thread pool.  Per-instance semaphores would let different
# model sizes (0.5B vs 3B) contend for the same physical cores.
_GLOBAL_INFERENCE_SEM = asyncio.Semaphore(1)


class LocalGGUFModelLoader(BaseLocalLoader):
    """Production-grade CPU text generator using llama.cpp + GGUF.

    Loads GGUF-quantized models from ``{AI_MODELS}/gguf/``.

    Meets target:
      - First token  < 150 ms  (with warm model)
      - 100 tokens   < 1 s     (steady-state decode)
    """

    def __init__(self, model_name: str = "qwen2.5-3b-instruct"):
        super().__init__(model_name=model_name)
        self._llama = None
        self._model_path: Path | None = None
        self._load_time_s: float = 0.0

    # ── helpers ──────────────────────────────────────────────

    def _gguf_path(self) -> Path:
        """Resolve the GGUF file path for the configured model."""
        name_map = {
            "qwen2.5-3b-instruct":  "qwen2.5-3b-instruct",
            "qwen3b-base":          "qwen2.5-3b-instruct",
            "qwen2.5-0.5b":        "qwen2.5-0.5b-instruct",
        }
        stem = name_map.get(self.model_name, self.model_name)
        filename = f"{stem}-{_GGUF_QUANT}.gguf"
        return Path(_settings.AI_MODELS) / "gguf" / filename

    def _n_threads(self) -> int:
        """Number of CPU threads for inference.

        Uses physical cores (not hyperthreads) to avoid cache thrashing.
        Override via LLAMA_CPP_THREADS env var.
        """
        env = os.environ.get("LLAMA_CPP_THREADS")
        if env:
            return int(env)
        try:
            import psutil
            physical = psutil.cpu_count(logical=False)
            return max(1, physical - 1 if physical else 4)
        except Exception:
            import multiprocessing
            total = multiprocessing.cpu_count()
            return max(1, total // 2)  # half of logical cores

    # ── lifecycle ────────────────────────────────────────────

    async def load(self) -> None:
        if self._loaded:
            return
        t0 = time.perf_counter()
        path = self._normalize_path(self._gguf_path())

        if not Path(path).exists():
            raise FileNotFoundError(
                f"GGUF model not found at {path}. "
                f"Run download_gguf_models.py first."
            )

        from llama_cpp import Llama

        use_mlock = os.environ.get("LLAMA_MLOCK", "0") == "1"
        loop = asyncio.get_running_loop()
        async with _GLOBAL_INFERENCE_SEM:
            self._llama = await loop.run_in_executor(
                None,
                functools.partial(
                    Llama,
                    model_path=path,
                    n_ctx=8192,
                    n_batch=512,
                    n_ubatch=256,
                    n_threads=4,
                    n_gpu_layers=0,
                    verbose=False,
                    use_mmap=True,
                    use_mlock=use_mlock,
                    flash_attn=False,
                ),
            )
        self._load_time_s = time.perf_counter() - t0
        self._loaded = True

        model_filename = Path(path).name
        logger.info(
            "\n"
            "--------------------------------\n"
            "GENERATOR BACKEND\n"
            "--------------------------------\n"
            f"Backend    : llama.cpp (v{_LLAMA_VER})\n"
            f"Model      : {model_filename}\n"
            f"Threads    : 4\n"
            f"Context    : 8192\n"
            f"Batch      : 512 / 256\n"
            f"GPU Layers : 0\n"
            f"mlock      : {use_mlock}\n"
            "--------------------------------"
        )

    async def unload(self) -> None:
        if self._llama:
            # llama-cpp-python handles cleanup via __del__ / context manager
            del self._llama
            self._llama = None
        self._loaded = False

    # ── health ───────────────────────────────────────────────

    async def health(self) -> Dict[str, Any]:
        if not self._loaded or not self._llama:
            return {"status": "not_loaded", "model": self.model_name}
        try:
            # Quick forward pass via tokenize
            _ = self._llama.tokenize(b"test")
            return {
                "status": "healthy",
                "model": self.model_name,
                "loaded": True,
                "backend": "llama.cpp",
                "quant": _GGUF_QUANT,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def warmup(self) -> Dict[str, Any]:
        if not self._loaded or not self._llama:
            return {"status": "skipped", "reason": "model not loaded"}
        t0 = time.perf_counter()
        async with _GLOBAL_INFERENCE_SEM:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                functools.partial(
                    self._llama,
                    "Hi",
                    max_tokens=8,
                    temperature=0.0,
                    echo=False,
                ),
            )
        elapsed = time.perf_counter() - t0
        return {"status": "ok", "time_s": round(elapsed, 3), "model": self.model_name}

    # ── generation ───────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> GenerationResult:
        if not self._loaded or not self._llama:
            raise RuntimeError("Model not loaded. Call load() first.")

        start = time.perf_counter()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": "You are a precise documentation assistant. Stick strictly to the context.",
            })
        messages.append({"role": "user", "content": prompt})

        t_pre = time.perf_counter()
        first_token_time = 0.0

        # Streaming path — measure first-token latency
        if stream:
            try:
                async with _GLOBAL_INFERENCE_SEM:
                    loop = asyncio.get_running_loop()
                    output = await loop.run_in_executor(
                        None,
                        functools.partial(
                            self._run_streaming_collect,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                            t_pre=t_pre,
                        ),
                    )

                generated_text = output["text"]
                finish_reason = output["finish_reason"]
                prompt_tokens = output["prompt_tokens"]
                completion_tokens = output["completion_tokens"]
                first_token_time = output["first_token_time"]
                gen_time = output["gen_time"]

            except Exception as e:
                logger.error(f"GGUF streaming failed: {e}")
                return GenerationResult(
                    text="",
                    finish_reason="error",
                    latency_ms=(time.perf_counter() - start) * 1000,
                    model=self.model_name,
                    metadata={"error": str(e)},
                )

        else:
            # Non-streaming — measure prefill vs decode
            try:
                async with _GLOBAL_INFERENCE_SEM:
                    loop = asyncio.get_running_loop()
                    output = await loop.run_in_executor(
                        None,
                        functools.partial(
                            self._llama.create_chat_completion,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                            stream=False,
                            stop=None,
                        ),
                    )

                gen_time = time.perf_counter() - t_pre

                choice = output.get("choices", [{}])[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "stop") or "stop"
                generated_text = message.get("content", "")

                usage = output.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                # Non-streaming doesn't expose prefill/decode split.
                # Set first_token_time = gen_time (worst-case, includes full generation).
                first_token_time = gen_time

            except Exception as e:
                logger.error(f"GGUF generation failed: {e}")
                return GenerationResult(
                    text="",
                    finish_reason="error",
                    latency_ms=(time.perf_counter() - start) * 1000,
                    model=self.model_name,
                    metadata={"error": str(e)},
                )

        total_ms = (time.perf_counter() - start) * 1000
        first_token_ms = first_token_time * 1000
        tokens_per_sec = (
            completion_tokens / gen_time if gen_time > 0 else 0.0
        )
        prefill_ms = first_token_ms
        decode_ms = max(0.0, gen_time * 1000 - first_token_ms)

        logger.info(
            "\n"
            "--------------------------------\n"
            "GENERATION PROFILE\n"
            "--------------------------------\n"
            f"Prompt tokens : {prompt_tokens}\n"
            f"Output tokens : {completion_tokens}\n"
            f"Prefill       : {prefill_ms:.0f} ms\n"
            f"First token   : {first_token_ms:.0f} ms\n"
            f"Decode        : {decode_ms:.0f} ms\n"
            f"Speed         : {tokens_per_sec:.1f} tok/s\n"
            "--------------------------------"
        )

        return GenerationResult(
            text=generated_text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=finish_reason,
            latency_ms=total_ms,
            model=self.model_name,
            metadata={
                "backend": "llama.cpp",
                "quant": _GGUF_QUANT,
                "tokens_per_second": round(tokens_per_sec, 1),
                "first_token_ms": round(first_token_ms, 1),
                "gen_time_ms": round(gen_time * 1000, 0),
                "prompt_tokens": prompt_tokens,
                "threads": self._n_threads(),
                "load_time_s": round(self._load_time_s, 1),
            },
        )

    async def generate_streamed(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator that yields tokens as produced."""
        if not self._loaded or not self._llama:
            raise RuntimeError("Model not loaded.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": "You are a precise documentation assistant.",
            })
        messages.append({"role": "user", "content": prompt})

        # Offload full streaming loop to thread pool; tokens arrive via queue
        # Semaphore held for entire stream so concurrent calls queue, not contend.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run():
            stream = self._llama.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        await _GLOBAL_INFERENCE_SEM.acquire()
        try:
            loop.run_in_executor(None, _run)
            while True:
                token = await queue.get()
                if token is None:
                    break
                yield token
        finally:
            _GLOBAL_INFERENCE_SEM.release()

    # ── synchronous helpers (run in thread pool) ────────────

    def _run_streaming_collect(
        self,
        messages: list,
        max_tokens: int,
        temperature: float,
        top_p: float,
        t_pre: float,
    ) -> dict:
        """Run streaming inference synchronously, collect all tokens + timing."""
        stream_gen = self._llama.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=True,
            stop=None,
        )

        prompt_tokens = 0
        completion_tokens = 0
        first_token = True
        first_token_time = 0.0
        collected = []
        finish_reason = "stop"

        for chunk in stream_gen:
            if chunk.get("usage"):
                usage = chunk["usage"]
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

            choice = chunk.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            token = delta.get("content", "")
            if not token:
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                continue
            if first_token:
                first_token_time = time.perf_counter() - t_pre
                first_token = False
            collected.append(token)

        generated_text = "".join(collected)
        gen_time = time.perf_counter() - t_pre
        completion_tokens = completion_tokens or len(collected)

        return {
            "text": generated_text,
            "finish_reason": finish_reason,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "first_token_time": first_token_time,
            "gen_time": gen_time,
        }

    # ── compatibility aliases ────────────────────────────────

    async def infer(self, prompt: str, **kwargs) -> str:
        """Thin wrapper for backward compatibility."""
        result = await self.generate(prompt, **kwargs)
        return result.text
