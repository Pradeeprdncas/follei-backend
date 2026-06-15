# app/services/rag/llm/generator.py
import httpx
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()

async def generate_answer(question: str, context: str, system_prompt: str) -> str:
    """
    Generates an answer using the custom system prompt generated on the fly 
    by the optimization layer.
    """
    
    # Include un-bypassable ground truth guardrails to ensure verification safety
    compiled_system_prompt = (
        f"{system_prompt}\n\n"
        "ABSOLDUTE GROUND RULES:\n"
        "- Never mention external software, tools, infrastructure dependencies, or protocols "
        "unless explicitly declared in the context document chunks provided.\n"
        "- If the text doesn't show a metric, value, or status, treat it as non-existent.\n"
        "- Do not offer general industry recommendations or additions unless explicitly ordered."
    )

    prompt = f"""Context reference segments:
\"\"\"
{context}
\"\"\"

User Query: {question}

Formulate your technical answer below:"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": compiled_system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.1, # Drop temperature slightly for tighter compliance
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise