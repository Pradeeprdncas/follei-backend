"""Prompt templates for all execution modes.

Each module exposes SYSTEM_PROMPT (str).
"""
from . import general_prompt
from . import knowledge_prompt
from . import reasoning_prompt
from . import hybrid_prompt
from . import policy

__all__ = [
    "general_prompt",
    "knowledge_prompt",
    "reasoning_prompt",
    "hybrid_prompt",
    "policy",
]
