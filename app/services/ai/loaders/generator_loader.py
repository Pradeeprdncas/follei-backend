"""generator_loader.py — backward-compat shim (CLOUD API REMOVED).

All calls are forwarded to LocalGGUFModelLoader which uses
llama.cpp + GGUF for local generation via ModelManager.

DO NOT re-introduce httpx or Mistral API calls here.
"""
# LEGACY TRANSFORMERS: LocalGeneratorLoader was removed.
# See local_generator_loader.py for the archived implementation.
from app.services.ai.loaders.local_gguf_model_loader import LocalGGUFModelLoader  # noqa: F401

# Alias kept for test-suite backward compatibility
GeneratorLoader = LocalGGUFModelLoader