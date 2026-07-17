"""Corrective RAG loop — diagnose failure type, act differently per type.

NO_RELEVANT_CHUNKS  → escalate/live-data immediately
PARTIAL_RELEVANCE   → reformulate targeting the gap, retry once
QUERY_AMBIGUOUS     → don't retry, ask clarification or state ambiguity
"""

from enum import Enum
from typing import Any
from dataclasses import dataclass

from loguru import logger

from app.config.settings import get_settings

_settings = get_settings()

RELEVANCE_THRESHOLD = 0.35
AMBIGUITY_THRESHOLD = 0.6
MIN_CHUNKS_ABOVE_THRESHOLD = 1
MAX_RETRIES = 2
INSUFFICIENT_RESPONSE = (
    "I don't have enough information in my knowledge base to answer that "
    "question accurately. Please rephrase your question or provide more details."
)


class FailureType(str, Enum):
    NO_RELEVANT_CHUNKS = "no_relevant_chunks"
    PARTIAL_RELEVANCE = "partial_relevance"
    QUERY_AMBIGUOUS = "query_ambiguous"
    NONE = "none"


@dataclass
class Action:
    failure_type: FailureType
    reformulation: str | None
    escalate: bool
    ask_clarification: bool
    reason: str


def grade_chunks(
    chunks: list[dict[str, Any]],
    threshold: float = RELEVANCE_THRESHOLD,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """Grade retrieved chunks by relevance score.

    Returns:
        (passing_chunks, failing_chunks, max_score)
    """
    if not chunks:
        return [], [], 0.0

    passing: list[dict[str, Any]] = []
    failing: list[dict[str, Any]] = []
    max_score = 0.0

    for chunk in chunks:
        score = chunk.get("score", 0.0)
        if score > max_score:
            max_score = score
        if score >= threshold:
            passing.append(chunk)
        else:
            failing.append(chunk)

    logger.info(
        "Graded {} chunks: {} passing (>{:.2f}), {} below",
        len(chunks), len(passing), threshold, len(failing),
    )
    return passing, failing, max_score


def diagnose_failure(
    chunks: list[dict[str, Any]],
    query: str,
) -> FailureType:
    """Diagnose why retrieval failed.

    Examines chunk scores and patterns to classify the failure into one of
    three types for targeted corrective action.
    """
    if not chunks:
        return FailureType.NO_RELEVANT_CHUNKS

    scores = [c.get("score", 0.0) for c in chunks]
    max_score = max(scores)
    median_score = sorted(scores)[len(scores) // 2] if scores else 0.0

    # NO_RELEVANT_CHUNKS: nothing above the relevance floor
    if max_score < RELEVANCE_THRESHOLD:
        return FailureType.NO_RELEVANT_CHUNKS

    # PARTIAL_RELEVANCE: some relevant but overall weak
    if max_score < AMBIGUITY_THRESHOLD and median_score < 0.4:
        return FailureType.PARTIAL_RELEVANCE

    # QUERY_AMBIGUOUS: scores are high but chunks contradict or don't answer
    if max_score >= AMBIGUITY_THRESHOLD:
        texts = [c.get("text", "")[:200] for c in chunks[:3]]
        contradiction_score = _detect_contradiction(texts)
        if contradiction_score > 0.3:
            return FailureType.QUERY_AMBIGUOUS

    return FailureType.NONE


def _detect_contradiction(texts: list[str]) -> float:
    """Simple heuristic contradiction detection.

    Returns a score 0-1 where higher = more contradictory.
    """
    if len(texts) < 2:
        return 0.0

    neg_pairs = 0
    total_checks = 0
    negations = {"not", "never", "cannot", "doesn't", "don't", "won't", "isn't", "aren't", "no"}

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            words_i = set(texts[i].lower().split())
            words_j = set(texts[j].lower().split())
            common = words_i & words_j
            if len(common) < 2:
                continue
            total_checks += 1
            has_neg_i = bool(words_i & negations)
            has_neg_j = bool(words_j & negations)
            if has_neg_i != has_neg_j:
                neg_pairs += 1

    return neg_pairs / max(total_checks, 1)


def act_on_failure(
    failure_type: FailureType,
    original_query: str,
    retry_count: int,
) -> Action:
    """Determine corrective action based on failure type and retry count."""
    if failure_type == FailureType.NO_RELEVANT_CHUNKS:
        if retry_count < MAX_RETRIES:
            reformulation = _reformulate_broader(original_query)
            return Action(
                failure_type=failure_type,
                reformulation=reformulation,
                escalate=False,
                ask_clarification=False,
                reason=f"No chunks found — broadened query (attempt {retry_count + 1})",
            )
        return Action(
            failure_type=failure_type,
            reformulation=None,
            escalate=True,
            ask_clarification=False,
            reason="No chunks found after retries — escalating to live data",
        )

    if failure_type == FailureType.PARTIAL_RELEVANCE:
        if retry_count < MAX_RETRIES:
            reformulation = _reformulate_target_gap(original_query)
            return Action(
                failure_type=failure_type,
                reformulation=reformulation,
                escalate=False,
                ask_clarification=False,
                reason=f"Partial relevance — reformulated targeting gap (attempt {retry_count + 1})",
            )
        return Action(
            failure_type=failure_type,
            reformulation=None,
            escalate=True,
            ask_clarification=False,
            reason="Partial relevance after retries — escalating",
        )

    if failure_type == FailureType.QUERY_AMBIGUOUS:
        return Action(
            failure_type=failure_type,
            reformulation=None,
            escalate=False,
            ask_clarification=True,
            reason="Query ambiguous — asking for clarification instead of retrying",
        )

    return Action(
        failure_type=FailureType.NONE,
        reformulation=None,
        escalate=False,
        ask_clarification=False,
        reason="No failure — proceeding with retrieved context",
    )


def _reformulate_broader(query: str) -> str:
    """Expand a query to broader terms for better recall."""
    words = query.split()
    if len(words) <= 3:
        prefixes = [
            "Tell me about",
            "What is",
            "Information about",
        ]
        return f"{prefixes[hash(query) % len(prefixes)]} {query}"

    if query.lower().startswith(("how ", "why ")):
        return f"Explain {query[0].lower() + query[1:]}"

    return query


def _reformulate_target_gap(query: str) -> str:
    """Reformulate to target the specific gap in retrieved context."""
    words = query.split()
    if words[-1].lower() in ("it", "this", "that", "they", "them"):
        return f"{query} (details, explanation, specifics)"
    if len(words) <= 4:
        return f"{query} details explanation specifics"
    return query


def needs_correction(
    passing: list[dict[str, Any]],
    max_score: float,
    min_chunks: int = MIN_CHUNKS_ABOVE_THRESHOLD,
) -> bool:
    """Determine if the corrective loop should trigger."""
    if len(passing) >= min_chunks:
        return False
    if max_score >= RELEVANCE_THRESHOLD:
        return False
    return True


def reformulate_query(original_query: str, context_hint: str = "") -> str:
    """Legacy reformulation — kept for backward compat."""
    return _reformulate_broader(original_query)


class CorrectiveLoop:
    """Corrective RAG loop with failure-type diagnosis and targeted retries.

    NO_RELEVANT_CHUNKS → broaden query, retry up to MAX_RETRIES, then escalate
    PARTIAL_RELEVANCE → reformulate targeting the gap, retry once, then escalate
    QUERY_AMBIGUOUS → never retry, ask clarification
    """

    def __init__(
        self,
        relevance_threshold: float = RELEVANCE_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._threshold = relevance_threshold
        self._max_retries = max_retries

    async def execute(
        self,
        query: str,
        retrieve_fn,
        top_k: int = 4,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Run the corrective RAG loop with failure-type diagnosis.

        Args:
            query: User question.
            retrieve_fn: Async callable(query, top_k, tenant_id) → list[chunk_dict].
            top_k: Number of chunks to retrieve per attempt.
            tenant_id: Tenant scope.

        Returns:
            dict with keys: chunks, corrected (bool), retries (int),
                            gave_up (bool), final_query (str),
                            failure_type (str), correction_path (str)
        """
        current_query = query
        retries = 0
        gave_up = False

        for attempt in range(self._max_retries + 1):
            chunks = await retrieve_fn(current_query, top_k=top_k, tenant_id=tenant_id)

            passing, _, max_score = grade_chunks(chunks, self._threshold)

            if not needs_correction(passing, max_score):
                return {
                    "chunks": passing if passing else chunks,
                    "corrected": attempt > 0,
                    "retries": retries,
                    "gave_up": False,
                    "final_query": current_query,
                    "failure_type": FailureType.NONE.value,
                    "correction_path": "none",
                }

            if attempt < self._max_retries:
                failure_type = diagnose_failure(chunks, current_query)
                action = act_on_failure(failure_type, current_query, retries)

                if action.ask_clarification:
                    logger.info(
                        "Corrective loop: ambiguous query — asking clarification "
                        "(failure_type={})", failure_type.value,
                    )
                    return {
                        "chunks": chunks or [],
                        "corrected": True,
                        "retries": retries,
                        "gave_up": True,
                        "final_query": current_query,
                        "failure_type": failure_type.value,
                        "correction_path": "ambiguous",
                    }

                if action.reformulation:
                    retries += 1
                    current_query = action.reformulation
                    logger.info(
                        "Corrective loop: retry {} (failure_type={}, action={})",
                        retries, failure_type.value, action.reason,
                    )
                else:
                    gave_up = True
                    logger.info(
                        "Corrective loop: giving up after {} retries (failure_type={})",
                        retries, failure_type.value,
                    )
                    return {
                        "chunks": [],
                        "corrected": retries > 0,
                        "retries": retries,
                        "gave_up": gave_up,
                        "final_query": current_query,
                        "failure_type": failure_type.value,
                        "correction_path": action.reason,
                    }
            else:
                gave_up = True
                failure_type = diagnose_failure(chunks, current_query)
                logger.info(
                    "Corrective loop: giving up after {} retries (failure_type={}, max_score={:.3f})",
                    retries, failure_type.value, max_score,
                )

        return {
            "chunks": [],
            "corrected": retries > 0,
            "retries": retries,
            "gave_up": gave_up,
            "final_query": current_query,
            "failure_type": FailureType.NONE.value,
            "correction_path": "exhausted_retries",
        }
