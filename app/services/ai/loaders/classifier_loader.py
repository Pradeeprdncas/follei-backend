"""classifier_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalClassifierLoader which uses
ModernBERT-base for local classification via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
from app.services.ai.loaders.local_classifier_loader import LocalClassifierLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
ClassifierLoader = LocalClassifierLoader