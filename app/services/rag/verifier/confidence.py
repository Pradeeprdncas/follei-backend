"""Verification agent — checks if answer is supported by context."""
import httpx
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def verify_answer(question: str, context: str, answer: str) -> dict:
    """
    Second LLM call to verify the answer is fully supported by context.
    Returns {"supported": bool, "confidence": float, "reason": str}.
    """
    prompt = f"""You are a verification agent. Your job is to check if the ANSWER is fully supported by the CONTEXT provided.

Context:
{context[:6000]}

Question: {question}

Proposed Answer: {answer}

Instructions:
1. Check every claim in the answer against the context.
2. If ALL claims are supported, respond: YES
3. If ANY claim is NOT supported or is hallucinated, respond: NO
4. Provide a confidence score from 0.0 to 1.0
5. Give a brief reason.

Format your response EXACTLY as:
SUPPORTED: YES or NO
CONFIDENCE: 0.0-1.0
REASON: <brief explanation>"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"},
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {
                            "role": "system", 
                            "content": (
                                "You are a precise technical verification agent. Your job is to ensure the core claims "
                                "in the answer match the source context. Do not penalize the answer for organizing "
                                "raw lists into clean markdown layouts, but strictly reject it if it hallucinates "
                                "entirely new feature logic, fake HTTP verbs (GET/POST) not present in the text, "
                                "or unmentioned service workflows."
                            )
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 256,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Parse the response safely
            supported = False
            confidence = 0.5
            reason = ""

            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                # Check target prefix flags cleanly regardless of case spacing
                if line.upper().startswith("SUPPORTED:"):
                    supported = "YES" in line.upper()
                elif line.upper().startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.split(":")[1].strip())
                    except:
                        pass
                elif line.upper().startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()

            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))

            logger.info(f"Verification: supported={supported}, confidence={confidence}")
            return {
                "supported": supported,
                "confidence": confidence,
                "reason": reason if reason else "Verified successfully by LLM agent.",
            }
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return {"supported": False, "confidence": 0.0, "reason": f"Verification error: {str(e)}"}