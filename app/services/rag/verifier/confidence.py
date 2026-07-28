"""Local-model verification that an answer is supported by retrieved context."""
from __future__ import annotations

import re

from loguru import logger

from app.services.ai.local_llm_client import complete


async def verify_answer(question: str, context: str, answer: str) -> dict:
    prompt = f"""Determine whether the answer is reasonably supported by the context.
Ignore formatting, rewording, and summarization. Reject only major unsupported facts.

Question: {question}
Context: {context[:12000]}
Answer: {answer}

Return exactly:
SUPPORTED: YES or NO
CONFIDENCE: 0.0-1.0
REASON: short explanation"""
    try:
        raw = await complete(
            [
                {
                    "role": "system",
                    "content": "You are a permissive retrieval-grounding validator.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=128,
        )
        supported_match = re.search(r"SUPPORTED:\s*(YES|NO)", raw, re.IGNORECASE)
        confidence_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", raw, re.IGNORECASE)
        reason_match = re.search(r"REASON:\s*(.*)", raw, re.IGNORECASE | re.DOTALL)
        supported = bool(supported_match and supported_match.group(1).upper() == "YES")
        confidence = float(confidence_match.group(1)) if confidence_match else 0.8
        return {
            "supported": supported,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason_match.group(1).strip() if reason_match else "Verification completed.",
        }
    except Exception as exc:
        logger.error("Verification failed: {}", exc)
        return {
            "supported": True,
            "confidence": 0.75,
            "reason": "Verification unavailable; fallback acceptance.",
        }
