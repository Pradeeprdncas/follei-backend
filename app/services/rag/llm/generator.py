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
    compiled_system_prompt = f"""
{system_prompt}

YOU ARE A RETRIEVAL AUGMENTED GENERATION ENGINE.

You are forbidden from using world knowledge.

You may only transform,
summarize,
reorganize,
or quote the provided context.

If a fact is not explicitly contained in context,
you must state:

"The context does not specify."

Never infer.

Never assume.

Never extrapolate.

Never create examples.

Never fill gaps.

STRICT FACTUALITY RULES

If a requested item
is not explicitly present
in retrieved context:

Output:

NOT FOUND IN RETRIEVED DOCUMENTS

Do not infer.
Do not complete.
Do not summarize missing sections.
Do not use world knowledge.

Every bullet point must
be traceable to retrieved text.
"""

    prompt = f"""
    CONTEXT

    {context}

    QUESTION

    {question}

    INSTRUCTIONS

    Use ONLY information found in CONTEXT.

    Every statement must be directly supported by CONTEXT.

    If information is missing say:

    "The retrieved documents do not contain this information."

    Never infer.

    Never speculate.

    Never use outside knowledge.

    Never complete partially described systems.

    Return a structured answer.
"""

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