"""Prompt management — single source of truth for all system prompts."""
from app.services.ai.prompts.manager import PromptManager, get_prompt_manager

__all__ = ["PromptManager", "get_prompt_manager"]
