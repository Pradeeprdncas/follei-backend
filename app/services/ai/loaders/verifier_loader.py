"""verifier_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalVerifierLoader which uses
smollm2-360m for local verification via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
from app.services.ai.loaders.local_verifier_loader import LocalVerifierLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
VerifierLoader = LocalVerifierLoader