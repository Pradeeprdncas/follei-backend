"""PromptManager — centralized prompt template management.

Every prompt template in the system lives here or references here.
No hardcoded prompts in services — use get_prompt().

Sources:
- app/services/rag/llm/prompts/ (legacy, kept for backward compat)
- This module (canonical for new prompts)
"""
from typing import Dict, Optional, Any
from loguru import logger


_PROMPT_REGISTRY: Dict[str, str] = {}


def register_prompt(name: str, template: str) -> None:
    _PROMPT_REGISTRY[name] = template


def get_prompt(name: str, **kwargs: Any) -> str:
    template = _PROMPT_REGISTRY.get(name)
    if template is None:
        raise KeyError(f"Prompt not found: {name}")
    if kwargs:
        return template.format(**kwargs)
    return template


def list_prompts() -> Dict[str, str]:
    return dict(_PROMPT_REGISTRY)


class PromptManager:
    """Centralized prompt management.

    - Registers all system prompts at startup
    - Provides get() / register() / list() for discovery
    - Enforces no hardcoded prompts outside this module
    """

    def __init__(self):
        self._register_defaults()

    def _register_defaults(self) -> None:
        from app.services.rag.llm.prompts.general_prompt import SYSTEM_PROMPT as GENERAL
        from app.services.rag.llm.prompts.knowledge_prompt import SYSTEM_PROMPT as KNOWLEDGE
        from app.services.rag.llm.prompts.reasoning_prompt import SYSTEM_PROMPT as REASONING
        from app.services.rag.llm.prompts.hybrid_prompt import SYSTEM_PROMPT as HYBRID
        from app.services.rag.llm.prompts.policy import POLICY_BLOCK

        register_prompt("general", GENERAL)
        register_prompt("knowledge", KNOWLEDGE)
        register_prompt("reasoning", REASONING)
        register_prompt("hybrid", HYBRID)
        register_prompt("policy_block", POLICY_BLOCK)

    def get(self, name: str, **kwargs: Any) -> str:
        return get_prompt(name, **kwargs)

    def register(self, name: str, template: str) -> None:
        register_prompt(name, template)

    def list(self) -> Dict[str, str]:
        return list_prompts()


_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    global _manager
    if _manager is None:
        _manager = PromptManager()
    return _manager
