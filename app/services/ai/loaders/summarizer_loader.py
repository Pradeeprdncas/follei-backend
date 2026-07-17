"""summarizer_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalSummarizerLoader which uses
smollm2-360m for local summarization via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
from app.services.ai.loaders.local_summarizer_loader import LocalSummarizerLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
SummarizerLoader = LocalSummarizerLoader