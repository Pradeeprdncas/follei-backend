"""query_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalQueryOptimizerLoader which uses
qwen2.5-0.5b for local query optimization via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
from app.services.ai.loaders.local_query_loader import LocalQueryOptimizerLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
QueryOptimizerLoader = LocalQueryOptimizerLoader