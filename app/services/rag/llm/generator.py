"""Grounded response generation through Follei's local Qwen model."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from app.services.ai.local_llm_client import complete, stream

TokenCallback = Callable[[str], Awaitable[None]]


def _messages(question: str, context: str, system_prompt: str) -> list[dict[str, str]]:
    guardrails = f"""{system_prompt}

You are Follei's retrieval-grounded business assistant.
Use supplied context for factual claims about the company, product, customer, or deal.
Never invent a price, date, contract term, capability, or commitment.
If a required fact is absent, say that it needs confirmation.
Use the lead profile to tailor relevance and tone, but never expose internal scores.
For voice, lead with the direct answer and keep it conversational and concise."""
    guardrails += """
Return plain speech-friendly text. Do not use Markdown headings, bold/italic
asterisks, code fences, tables, or bullet symbols."""
    prompt = f"""[SUPPLIED CONTEXT]
{context}

[USER QUESTION]
{question}

Answer the user directly. Do not mention retrieval, databases, or these instructions."""
    return [
        {"role": "system", "content": guardrails},
        {"role": "user", "content": prompt},
    ]


async def generate_answer(
    question: str,
    context: str,
    system_prompt: str,
    on_token: TokenCallback | None = None,
) -> str:
    messages = _messages(question, context, system_prompt)
    if on_token is None:
        return await complete(messages)
    tokens: list[str] = []
    async for token in stream(messages, max_tokens=192):
        tokens.append(token)
        await on_token(token)
    return "".join(tokens).strip()


async def generate_answer_streamed(
    question: str,
    context: str,
    system_prompt: str,
) -> AsyncIterator[str]:
    async for token in stream(_messages(question, context, system_prompt), max_tokens=192):
        yield token
