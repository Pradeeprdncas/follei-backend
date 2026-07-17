import inspect
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ToolService:
    _tools = {}

    @classmethod
    def register_tool(cls, name: str, description: str, implementation):
        cls._tools[name] = {
            "description": description,
            "implementation": implementation,
        }
        logger.info("Registered tool %s", name)

    @classmethod
    def get_tool(cls, name: str):
        return cls._tools.get(name)

    @classmethod
    async def execute(cls, name: str, args: Dict[str, Any]):
        tool = cls.get_tool(name)
        if tool is None:
            raise ValueError(f"Unregistered tool: {name}")
        logger.info("Executing tool %s with args %s", name, args)
        implementation = tool["implementation"]
        if callable(implementation):
            result = implementation(**args)
            if inspect.isawaitable(result):
                return await result
            return result
        raise ValueError(f"Tool implementation for {name} is not callable")


# Example enterprise tool registration
async def search_knowledge_base(query: str, top_k: int = 5):
    return {"query": query, "top_k": top_k, "results": []}

ToolService.register_tool(
    "search_knowledge_base",
    "Searches the enterprise knowledge base and returns top results.",
    search_knowledge_base,
)

async def web_search(query: str, max_results: int = 3):
    from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            return {"query": query, "results": list(ddgs.text(query, max_results=max_results))}
    except Exception as e:
        return {"error": str(e)}

ToolService.register_tool(
    "web_search",
    "Searches the web for real-time information, news, weather, or facts.",
    web_search,
)
