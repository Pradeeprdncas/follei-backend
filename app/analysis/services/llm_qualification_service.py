"""LLM-powered qualification scoring for BANT, MEDDIC, and similar frameworks.

Uses the local Qwen2.5-0.5B model via AIGateway to score each component
of a qualification framework (e.g., Budget, Authority, Need, Timeline for BANT)
based solely on the conversation transcript — no invented facts.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FRAMEWORK_COMPONENTS: dict[str, dict[str, str]] = {
    "BANT": {
        "budget": "Does the prospect have budget allocated or approved for this solution?",
        "authority": "Does the prospect have decision-making authority or access to the decision maker?",
        "need": "Does the prospect have a clear business need that this solution addresses?",
        "timeline": "Does the prospect have a defined purchase timeline?",
    },
    "MEDDIC": {
        "metrics": "What quantified business metrics does the prospect track and want to improve?",
        "economic_buyer": "Has the person with budget authority been identified and engaged?",
        "decision_criteria": "What formal evaluation criteria will the prospect use to decide?",
        "decision_process": "What are the stages, stakeholders, and timeline of the buying process?",
        "identify_pain": "What specific pain points has the prospect acknowledged?",
        "champion": "Is there an internal advocate driving the purchase forward?",
    },
}

_SYSTEM_PROMPT = (
    "You are a senior sales qualification analyst. "
    "Your task is to score a prospect conversation against a qualification framework. "
    "Return ONLY valid JSON — no markdown, no explanation outside the JSON. "
    "Use the exact format shown."
)


def _build_prompt(transcript: str, framework_name: str) -> str:
    components = _FRAMEWORK_COMPONENTS.get(framework_name)
    if not components:
        msg = f"Unknown framework: {framework_name}"
        raise ValueError(msg)

    component_lines = "\n".join(
        f'    "{key}": {{"score": <0-100>, "evidence": "<one-sentence quote or observation from transcript>"}}'
        for key in components
    )

    return (
        f"Transcript:\n{transcript}\n\n"
        f"Score each '{framework_name}' component 0-100 based ONLY on evidence in the transcript above. "
        f"0 = no evidence, 100 = confirmed. Each evidence string must be a direct quote or paraphrase from the transcript.\n\n"
        f"Output ONLY this JSON (no other text):\n"
        f"{{\n{component_lines}\n}}"
    )


class LLMQualificationService:
    @classmethod
    async def analyze(
        cls,
        transcript: str,
        framework_name: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        components = _FRAMEWORK_COMPONENTS.get(framework_name)
        if not components:
            return {
                "framework": framework_name,
                "error": f"Unknown framework: {framework_name}",
                "scores": {},
                "overall_score": None,
                "status": "error",
            }

        prompt = _build_prompt(transcript, framework_name)

        try:
            from app.services.ai import get_ai_service

            ai = get_ai_service()
            raw = await ai.generate(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                model_name="qwen2.5-0.5b",
                max_tokens=1024,
                temperature=0.1,
                top_p=0.9,
            )
        except Exception as exc:
            logger.warning("LLM qualification generation failed for %s: %s", framework_name, exc)
            return cls._fallback(transcript, framework_name, components, error=str(exc))

        return cls._parse_response(raw, transcript, framework_name, components)

    @classmethod
    def _parse_response(
        cls,
        raw: Any,
        transcript: str,
        framework_name: str,
        components: dict[str, str],
    ) -> dict[str, Any]:
        text = raw
        if hasattr(raw, "text"):
            text = raw.text
        text = str(text).strip()

        # Try extracting JSON from markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # Try parsing
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try extracting {...} block as last resort
            import re
            brace_match = re.search(r"\{[\s\S]*\}", text)
            if brace_match:
                try:
                    parsed = json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse LLM output for %s: %s", framework_name, text[:200])
                    return cls._fallback(transcript, framework_name, components, error="JSON parse failed")
            else:
                logger.warning("No JSON found in LLM output for %s: %s", framework_name, text[:200])
                return cls._fallback(transcript, framework_name, components, error="No JSON in output")

        scores: dict[str, dict[str, Any]] = {}
        valid_count = 0
        score_sum = 0.0

        for key in components:
            entry = parsed.get(key, {})
            if isinstance(entry, dict):
                score = entry.get("score")
                evidence = entry.get("evidence", "")
            elif isinstance(entry, (int, float)):
                score = entry
                evidence = ""
            else:
                score = None
                evidence = ""

            if score is not None and isinstance(score, (int, float)) and 0 <= score <= 100:
                valid_count += 1
                score_sum += float(score)
            else:
                score = None

            scores[key] = {
                "score": round(float(score), 1) if score is not None else None,
                "evidence": str(evidence) if evidence else "",
            }

        overall = round(score_sum / valid_count, 1) if valid_count > 0 else None

        return {
            "framework": framework_name,
            "overall_score": overall,
            "scores": scores,
            "status": "completed" if overall is not None else "low_confidence",
        }

    @classmethod
    def _fallback(
        cls,
        transcript: str,
        framework_name: str,
        components: dict[str, str],
        error: str = "",
    ) -> dict[str, Any]:
        """Evidence-only fallback used when the optional local LLM is absent.

        A zero means the transcript supplied no evidence; it does not mean the
        prospect definitively lacks that property.  This is preferable to null
        UI metrics and, unlike a generative fallback, cannot invent facts.
        """
        patterns: dict[str, dict[str, tuple[str, ...]]] = {
            "BANT": {
                "budget": (r"\bbudget\b", r"[$â‚¹â‚¬Â£]\s?\d", r"\b\d[\d,]*(?:k|m|million|thousand)\b", r"\b(?:funds?|funding)\s+(?:is|are|has been)\s+(?:approved|allocated)"),
                "authority": (r"\bdecision[ -]?maker\b", r"\bI (?:can|will) (?:approve|sign|decide)", r"\b(?:CEO|CFO|CTO|owner|director|VP|vice president)\b", r"\b(?:sign[- ]?off|final approval)\b"),
                "need": (r"\bwe need\b", r"\b(?:pain|problem|challenge|issue|bottleneck)s?\b", r"\bmust\b", r"\blooking for\b", r"\bwant to (?:improve|reduce|increase|replace|automate)\b"),
                "timeline": (r"\b(?:this|next) (?:week|month|quarter|year)\b", r"\bwithin \d+ (?:days?|weeks?|months?)\b", r"\b(?:asap|immediately|urgent)\b", r"\bby (?:Q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b"),
            },
            "MEDDIC": {
                "metrics": (r"\b(?:ROI|KPI|revenue|conversion|productivity|cost savings?)\b", r"\b\d+(?:\.\d+)?%\b", r"\b(?:increase|reduce|improve|save)\b.{0,40}\b\d", r"[$â‚¹â‚¬Â£]\s?\d"),
                "economic_buyer": (r"\beconomic buyer\b", r"\bdecision[ -]?maker\b", r"\bI (?:control|own|approve|sign)\b.{0,30}\bbudget\b", r"\b(?:CFO|CEO|owner)\b"),
                "decision_criteria": (r"\bdecision criteria\b", r"\b(?:evaluate|evaluation|requirements?|must[- ]?have|criteria)\b", r"\b(?:security|integration|compliance|price|scalability) (?:is|are|will be)\b", r"\bcompare\b"),
                "decision_process": (r"\bdecision process\b", r"\b(?:procurement|legal review|approval process|RFP|pilot|proof of concept)\b", r"\b(?:stakeholders?|committee|board)\b", r"\b(?:stages?|steps?) (?:are|include)\b"),
                "identify_pain": (r"\b(?:pain|problem|challenge|issue|bottleneck|frustrat\w*)s?\b", r"\b(?:losing|wasting|struggling|unable to)\b", r"\bneed to (?:fix|reduce|avoid|replace|automate)\b"),
                "champion": (r"\bchampion\b", r"\binternal (?:advocate|sponsor)\b", r"\b(?:I|we) will (?:push|drive|promote)\b.{0,35}\binternally\b", r"\b(?:sponsor|advocate) (?:for|of) (?:this|the project)\b"),
            },
        }
        framework_patterns = patterns.get(framework_name, {})
        scores: dict[str, dict[str, Any]] = {}
        for key in components:
            matched: list[re.Match[str]] = []
            for pattern in framework_patterns.get(key, ()):
                match = re.search(pattern, transcript, flags=re.IGNORECASE)
                if match:
                    matched.append(match)
            score = min(100.0, 55.0 + 20.0 * len(matched)) if matched else 0.0
            evidence = ""
            if matched:
                start = max(0, min(match.start() for match in matched) - 50)
                end = min(len(transcript), max(match.end() for match in matched) + 70)
                evidence = transcript[start:end].strip()
            scores[key] = {"score": round(score, 1), "evidence": evidence}
        overall = round(sum(item["score"] for item in scores.values()) / max(1, len(scores)), 1)
        return {
            "framework": framework_name,
            "fallback_reason": error,
            "overall_score": overall,
            "scores": scores,
            "status": "completed",
            "source": "evidence_heuristic",
        }

    @classmethod
    def get_components(cls, framework_name: str) -> dict[str, str]:
        return dict(_FRAMEWORK_COMPONENTS.get(framework_name, {}))
