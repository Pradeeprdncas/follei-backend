"""Small structured timing helper for the synchronous voice/chat RAG path."""
from __future__ import annotations
import time
from loguru import logger


class LatencyTrace:
    def __init__(self, *, trace_id: str, tenant_id: str) -> None:
        self.trace_id = trace_id
        self.tenant_id = tenant_id
        self._started = time.perf_counter()
        self._last = self._started
        self._stages: dict[str, float] = {}

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        self._stages[stage] = round((now - self._last) * 1000, 1)
        self._last = now

    def emit(self) -> None:
        total = round((time.perf_counter() - self._started) * 1000, 1)
        stages = " ".join(f"{key}={value}ms" for key, value in self._stages.items())
        logger.info(f"rag_latency trace={self.trace_id} tenant={self.tenant_id} {stages} total={total}ms")
