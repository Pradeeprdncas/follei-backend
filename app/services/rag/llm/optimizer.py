# app/services/rag/llm/optimizer.py
import httpx
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()

async def optimize_user_request(raw_question: str) -> dict:
    """
    Uses an LLM to correct typos, extract keywords for better embeddings search,
    and dynamically build an ideal System Prompt based on user intent.
    """
    system_instruction = (
        "You are an expert RAG Optimization Agent. Your job is to analyze messy user requests "
        "and split them into two components: an optimized semantic search query, and a hyper-targeted "
        "system prompt. Output your answer strictly as a valid JSON object."
    )

    analysis_prompt = f"""Analyze this raw user input: "{raw_question}"

Generate a JSON object with exactly two fields:
1. "optimized_search_query": Clean up all spelling mistakes, remove filler words like "explain everything about", and format it to maximize dense vector embedding match accuracy for technical documentation.
2. "tailored_system_prompt": Write a specific system prompt for the generation model. If the user request is wide-open or vague (e.g. "and everything"), explicitly instruct the generation model to ONLY talk about things found in the context, and forbid it from mentioning standard industry tools (like Kubernetes, Docker, webhooks, or SDKs) unless they are explicitly named in the context segments.

Example Output format:
{{
  "optimized_search_query": "Follei autonomous workspace platform architecture features",
  "tailored_system_prompt": "You are an expert technical assistant specializing in Follei Workspace. Restrict your summary strictly to facts, modules, and workflows written in the context. Do not invent deployment infrastructure, SDK details, or cloud platforms unless explicitly stated."
}}

Respond ONLY with the JSON block."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": analysis_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            import json
            result = json.loads(resp.json()["choices"][0]["message"]["content"].strip())
            logger.info(f"Optimized Query: {result.get('optimized_search_query')}")
            return result
    except Exception as e:
        logger.error(f"Request optimization failed: {e}")
        # Secure fallback if the LLM call fails
        return {
            "optimized_search_query": raw_question,
            "tailored_system_prompt": "You are a precise documentation assistant. Stick strictly to the context."
        }