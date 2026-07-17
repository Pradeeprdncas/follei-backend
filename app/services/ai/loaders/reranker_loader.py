"""reranker_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalRerankerLoader which uses
bge-reranker-base for local cross-encoder re-ranking via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
from app.services.ai.loaders.local_reranker_loader import LocalRerankerLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
RerankerLoader = LocalRerankerLoader