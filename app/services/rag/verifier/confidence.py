"""Verification agent — checks if answer is supported by context."""
import httpx
import re

from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()


async def verify_answer(
    question: str,
    context: str,
    answer: str
) -> dict:
    """
    Verification stage.

    Enterprise RAG rule:

    If retrieval succeeded and answer is grounded,
    do not aggressively reject useful answers.

    Verification is advisory, not a hard blocker.
    """

    prompt = f"""
You are a verification agent.

Determine whether the answer is reasonably supported
by the provided context.

Question:
{question}

Context:
{context[:12000]}

Answer:
{answer}

Rules:

- Ignore formatting differences.
- Ignore markdown tables.
- Ignore rewording.
- Ignore summarization.

Reject ONLY if the answer introduces major facts
that do not appear in the context.

Return EXACTLY:

SUPPORTED: YES or NO
CONFIDENCE: 0.0-1.0
REASON: short explanation
"""

    try:

        async with httpx.AsyncClient(timeout=30.0) as client:

            resp = await client.post(
                f"{_settings.MISTRAL_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_settings.MISTRAL_API_KEY}"
                },
                json={
                    "model": _settings.MISTRAL_CHAT_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a retrieval-grounding validator. "
                                "Be permissive when the answer is clearly "
                                "derived from context."
                            )
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 128
                }
            )

            resp.raise_for_status()

            data = resp.json()

            raw = data["choices"][0]["message"]["content"]

            logger.info("RAW VERIFIER RESPONSE")
            logger.info(raw)
            supported = False
            confidence = 0.8
            reason = "Verification completed."

            supported_match = re.search(
                r"SUPPORTED:\s*(YES|NO)",
                raw,
                re.IGNORECASE
            )

            confidence_match = re.search(
                r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)",
                raw,
                re.IGNORECASE
            )

            reason_match = re.search(
                r"REASON:\s*(.*)",
                raw,
                re.IGNORECASE | re.DOTALL
            )

            if supported_match:
                supported = (
                    supported_match.group(1).upper()
                    == "YES"
                )

            if confidence_match:
                confidence = float(
                    confidence_match.group(1)
                )

            if reason_match:
                reason = reason_match.group(1).strip()

            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence
                )
            )

            logger.info(
                f"Verification: "
                f"supported={supported}, "
                f"confidence={confidence}"
            )

            return {
                "supported": supported,
                "confidence": confidence,
                "reason": reason
            }

    except Exception as e:

        logger.error(
            f"Verification failed: {e}"
        )

        return {
            "supported": True,
            "confidence": 0.75,
            "reason": (
                "Verification unavailable, "
                "fallback acceptance."
            )
        }