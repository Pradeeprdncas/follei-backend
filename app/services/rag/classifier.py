"""Query classifier — 2-axis routing (needs_retrieval x needs_reasoning).

Deterministic first (regex), optional local model fallback for ambiguous
REASON_ONLY vs RETRIEVE_THEN_REASON boundary. Never queries the cloud.

Outputs one of four modes, decided before any retrieval or generation:
  RETRIEVE_ONLY         -- fact lookup, stick to text + cite
  REASON_ONLY           -- pure LLM knowledge, no context
  RETRIEVE_THEN_REASON  -- retrieve then reason over facts
  HYBRID                -- retrieve + general knowledge, label both
"""

import re
from enum import Enum
from dataclasses import dataclass

from loguru import logger


class RoutingMode(str, Enum):
    RETRIEVE_ONLY = "retrieve_only"
    REASON_ONLY = "reason_only"
    RETRIEVE_THEN_REASON = "retrieve_then_reason"
    HYBRID = "hybrid"


class QueryClass(Enum):
    """Kept for backward compat; new code should use RoutingMode."""
    SIMPLE_FACTUAL = "simple_factual"
    MULTI_HOP = "multi_hop"
    NEEDS_LIVE_DATA = "needs_live_data"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class ClassificationResult:
    query_class: QueryClass
    mode: RoutingMode
    needs_retrieval: bool
    needs_reasoning: bool
    top_k: int
    run_correction: bool
    confidence: float
    reason: str


_MODEL_CONFIDENCE_THRESHOLD = 0.8


# ── Hard blocks (never answered) ──────────────────────────────────────

_OUT_OF_SCOPE_PATTERNS = [
    r"\b(hack|password|credit card|ssn|social security)\b",
    r"\b(drugs|illegal|weapon)\b",
    r"\b(write (my|an) essay|do my homework)\b",
    r"\b(crack|license key|pirate)\b",
]


# ── Live data (always retrieve, never reason) ─────────────────────────

_LIVE_DATA_PATTERNS = [
    r"\b(weather|temperature|forecast)\b",
    r"\b(stock|share price|market|crypto|bitcoin)\b",
    r"\b(news|headline|breaking)\b",
    r"\b(traffic|flight|delay|schedule)\b",
    r"\b(sports score|game result|match)\b",
    r"\b(currency|exchange rate)\b",
    r"\b(time (in|at)|current time)\b",
    r"\b(what('s| is) (today|now|currently))\b",
]


# ── Strong retrieval signals (checked before REASON_ONLY) ─────────────
# These explicitly reference document content, independent of brand names.

_RETRIEVAL_SIGNAL_PATTERNS = [
    # Document/PDF references
    r"\b(in the (pdf|document|file|page|chapter|section|article|paper|book|text|upload|attachment|knowledge base))\b",
    r"\b(according to)\s+(the\s+)?(pdf|document|file|text|source|knowledge|database|upload)\b",
    r"\b(as (mentioned|described|stated|noted|per|shown|discussed))\s+(in|by)\b",
    r"\b(this (pdf|document|file|upload|text|page|chapter|section|article))\b",
    r"\b(refer (to|back)|see also|go through|look at|read through)\b",
    r"\b(from the (pdf|document|file|text|content|knowledge|source|database))\b",
    r"\b(extract|summarize|summarise|highlight)\s+(this|the)\s+(pdf|document|file|page|text|content)\b",
    r"\b(what does the (pdf|document|file|text|source|upload) say)\b",
    r"\b(does the (pdf|document|file|text|source|upload) (mention|contain|include))\b",
    r"\b(in this (pdf|document|file|chapter|section))\b",
    # Academic/scholarly references
    r"\b(B\.Sc|M\.Sc|PhD|B\.Tech|M\.Tech|Bachelor|Master|Doctor|Professor|Dr\.)\b",
    r"\b(course|syllabus|curriculum|lecture|lesson|module|unit|semester)\b",
    r"\b(textbook|reference book|study material|handout|notes)\b",
    r"\b(chapter|section|page|paragraph|figure|table|equation)\s+\d+",
    # Explicit knowledge base references
    r"\b(knowledge base|knowledge graph|corpus|index|repository)\b",
    r"\b(uploaded|indexed|stored|saved)\s+(document|file|pdf|content|data)\b",
]


# ── Strong REASON_ONLY signals (truly generic, no retrieval possible) ─

_REASON_ONLY_PATTERNS = [
    # Greetings and small talk
    r"\b(hi|hello|hey|greetings|good (morning|afternoon|evening))\b",
    r"\b(how are you|how's it going|what's up|sup)\b",
    r"\b(who are you|what are you|what can you do|tell me about yourself)\b",
    r"\b(thanks|thank you|thanks a lot|appreciate it)\b",
    # Creative / generative requests
    r"\b(write (a|an|some)\s+(poem|story|essay|song|lyrics|rap|joke|riddle))\b",
    r"\b(tell me a (joke|story|riddle|poem))\b",
    r"\b(compose|write|create)\s+(music|art|poem|song)\b",
    # Math calculations
    r"\b(calculate|compute|solve|what is)\s+\d+(\s*[+\-*/]\s*\d+)+",
    r"\b(solve\s+for\s+\w+)\b",
    # Translation
    r"\b(translate|convert)\s+['\"]?\w+['\"]?\s+(to|into)\s+['\"]?\w+['\"]?\b",
    # Opinions / advice (no document context)
    r"\b(give me (a|an|some))\s+(recipe|tip|advice|idea|suggestion|recommendation)\b",
    r"\b(how (to|can I|do I)\s+(cook|bake|make|build|create))\b",
    # Current events / personal
    r"\b(what (is|are)\s+(your|my)\s+(name|age|location|favorite))\b",
    r"\b(tell me (about |)(yourself|your (creator|maker|purpose)))\b",
]


# ── HYBRID: company + general knowledge ───────────────────────────────

_HYBRID_PATTERNS = [
    r"\b(how (does|can|would))\b.*\b(follei|coirei)\b",
    r"\b(what is)\b.*\b(follei|coirei)\b.*\b(and|vs|versus)\b",
    r"\b(compare|difference)\b.*\b(follei|coirei)\b.*\b(and|vs|with)\b",
    r"\b(can|does)\s+(follei|coirei)\s+(use|support|integrate|work with)\b",
]


# ── RETRIEVE_THEN_REASON: reasoning over facts ───────────────────────

_RETRIEVE_THEN_REASON_PATTERNS = [
    r"\b(why (does|did|would|is|are))\b",
    r"\b(what (would|will) happen if)\b",
    r"\b(compare|contrast|difference between)\b",
    r"\b(how does.*affect|impact of|effect on|relationship between)\b",
    r"\b(cause|consequence|result in|lead to)\b",
    r"\b(synthesize|combine|integrate|across)\b",
    r"\b(analyze|evaluate|assess)\b",
    r"\b(pros|cons|advantages?|disadvantages?|tradeoffs?)\b",
    r"\b(should|would|could)\s+(we|they|our|the)\b",
    r"\b(recommend|suggest|advise)\b",
    r"\b(feasib|viab|practic)\w+\b",
]


# ── RETRIEVE_ONLY: fact lookup patterns ───────────────────────────────

_RETRIEVE_ONLY_PATTERNS = [
    r"\b(what is|what are|define|definition|list|show|tell me about)\b",
    r"\b(how (to|do I|can I|does))\b",
    r"\b(when (did|was|is|does))\b",
    r"\b(where (is|are|can I))\b",
    r"\b(who (is|are|was|were))\b",
    r"\b(pricing|price|cost|plan|subscription)\b",
    r"\b(feature|capability|integration)\b",
    r"\b(api|sdk|webhook)\b",
    r"\b(install|setup|configure|deploy)\b",
    r"\b(documentation|doc|guide|tutorial)\b",
]


_COMPANY_NAMES_RE = re.compile(r"\b(follei|coirei|folio)\b", re.IGNORECASE)


class QueryClassifierService:
    """2-axis query classifier.

    Order of evaluation:
      1. Hard blocks (out of scope)
      2. Live data (always retrieve)
      3. Document retrieval signals (in pdf, according to, course codes, etc.)
      4. HYBRID (company + general)
      5. RETRIEVE_THEN_REASON + company name
      6. REASON_ONLY (truly generic: greetings, creative, math)
      7. RETRIEVE_THEN_REASON (reasoning without company)
      8. RETRIEVE_ONLY (fact lookup without company)
      9. Ambiguity fallback — defaults to RETRIEVE_THEN_REASON
    """

    def classify(self, query: str) -> ClassificationResult:
        try:
            return self._classify(query)
        except Exception:
            logger.exception("Classifier crashed -- returning safe default")
            return ClassificationResult(
                query_class=QueryClass.SIMPLE_FACTUAL,
                mode=RoutingMode.RETRIEVE_ONLY,
                needs_retrieval=True,
                needs_reasoning=False,
                top_k=5,
                run_correction=False,
                confidence=0.5,
                reason="Fallback after classifier exception",
            )

    def _classify(self, query: str) -> ClassificationResult:
        query_lower = query.lower().strip()
        if not query_lower:
            return self._out_of_scope("Empty query")

        # 1. Hard blocks
        for pattern in _OUT_OF_SCOPE_PATTERNS:
            if re.search(pattern, query_lower):
                return self._out_of_scope(f"Blocked by pattern: {pattern}")

        # 2. Live data -- always RETRIEVE_ONLY
        for pattern in _LIVE_DATA_PATTERNS:
            if re.search(pattern, query_lower):
                return self._mode_result(
                    mode=RoutingMode.RETRIEVE_ONLY,
                    query_class=QueryClass.NEEDS_LIVE_DATA,
                    top_k=15,
                    run_correction=True,
                    confidence=0.90,
                    reason=f"Live-data pattern: {pattern}",
                )

        has_company = bool(_COMPANY_NAMES_RE.search(query_lower))

        # 3. Strong retrieval signals (document references, academic context)
        #    These override REASON_ONLY -- checked before any REASON_ONLY gate.
        has_retrieval_signal = any(
            re.search(p, query_lower) for p in _RETRIEVAL_SIGNAL_PATTERNS
        )
        if has_retrieval_signal:
            # Document-specific lookup -- RETRIEVE_ONLY
            return self._retrieve_only_result(
                f"Retrieval signal detected: query references document content"
            )

        # 4. HYBRID: company + general knowledge topic
        for pattern in _HYBRID_PATTERNS:
            if re.search(pattern, query_lower):
                return self._mode_result(
                    mode=RoutingMode.HYBRID,
                    query_class=QueryClass.MULTI_HOP,
                    top_k=4,
                    run_correction=True,
                    confidence=0.85,
                    reason=f"Hybrid pattern: {pattern}",
                )

        # 5. RETRIEVE_THEN_REASON: reasoning over company facts
        for pattern in _RETRIEVE_THEN_REASON_PATTERNS:
            if re.search(pattern, query_lower) and has_company:
                return self._mode_result(
                    mode=RoutingMode.RETRIEVE_THEN_REASON,
                    query_class=QueryClass.MULTI_HOP,
                    top_k=4,
                    run_correction=True,
                    confidence=0.85,
                    reason=f"Reasoning pattern (company): {pattern}",
                )

        # 6. REASON_ONLY: truly generic queries (greetings, creative, math, etc.)
        #    Only matched when there is NO document-retrieval signal.
        for pattern in _REASON_ONLY_PATTERNS:
            if re.search(pattern, query_lower):
                return self._reason_only_result(f"Generic pattern: {pattern}")

        # 7. RETRIEVE_THEN_REASON: reasoning without company reference
        for pattern in _RETRIEVE_THEN_REASON_PATTERNS:
            if re.search(pattern, query_lower):
                return self._mode_result(
                    mode=RoutingMode.RETRIEVE_THEN_REASON,
                    query_class=QueryClass.MULTI_HOP,
                    top_k=4,
                    run_correction=True,
                    confidence=0.75,
                    reason=f"Reasoning pattern: {pattern}",
                )

        # 8. RETRIEVE_ONLY: factual lookups without company reference
        for pattern in _RETRIEVE_ONLY_PATTERNS:
            if re.search(pattern, query_lower):
                return self._retrieve_only_result(f"Factual pattern matched")

        # 9. Ambiguity fallback
        return self._ambiguity_fallback(query_lower, has_company)

    def _mode_result(
        self,
        mode: RoutingMode,
        query_class: QueryClass,
        top_k: int,
        run_correction: bool,
        confidence: float,
        reason: str,
    ) -> ClassificationResult:
        return ClassificationResult(
            query_class=query_class,
            mode=mode,
            needs_retrieval=mode in (RoutingMode.RETRIEVE_ONLY, RoutingMode.RETRIEVE_THEN_REASON, RoutingMode.HYBRID),
            needs_reasoning=mode in (RoutingMode.REASON_ONLY, RoutingMode.RETRIEVE_THEN_REASON, RoutingMode.HYBRID),
            top_k=top_k,
            run_correction=run_correction,
            confidence=confidence,
            reason=reason,
        )

    def _retrieve_only_result(self, reason: str) -> ClassificationResult:
        return self._mode_result(
            mode=RoutingMode.RETRIEVE_ONLY,
            query_class=QueryClass.SIMPLE_FACTUAL,
            top_k=4,
            run_correction=False,
            confidence=0.75,
            reason=reason,
        )

    def _reason_only_result(self, reason: str) -> ClassificationResult:
        return self._mode_result(
            mode=RoutingMode.REASON_ONLY,
            query_class=QueryClass.SIMPLE_FACTUAL,
            top_k=0,
            run_correction=False,
            confidence=0.80,
            reason=reason,
        )

    def _out_of_scope(self, reason: str) -> ClassificationResult:
        return ClassificationResult(
            query_class=QueryClass.OUT_OF_SCOPE,
            mode=RoutingMode.REASON_ONLY,
            needs_retrieval=False,
            needs_reasoning=False,
            top_k=0,
            run_correction=False,
            confidence=1.0,
            reason=reason,
        )

    def _ambiguity_fallback(
        self, query_lower: str, has_company: bool
    ) -> ClassificationResult:
        """Fallback when no pattern matched.

        Defaults to RETRIEVE_THEN_REASON (retrieval + reasoning) rather than
        REASON_ONLY, because a document RAG should bias toward retrieval
        when uncertain. REASON_ONLY is reserved for queries that explicitly
        match generic patterns above.
        """
        # Very short queries with no context -- default to retrieve
        if len(query_lower.split()) <= 2:
            return self._retrieve_only_result(
                "Ambiguity fallback -- short query, default RETRIEVE_ONLY"
            )

        logger.info(
            "Ambiguity fallback -- no pattern, default RETRIEVE_THEN_REASON: {}",
            query_lower[:100],
        )
        return self._mode_result(
            mode=RoutingMode.RETRIEVE_THEN_REASON,
            query_class=QueryClass.MULTI_HOP,
            top_k=4,
            run_correction=True,
            confidence=0.60,
            reason="Ambiguity fallback -- default RETRIEVE_THEN_REASON",
        )


_classifier: QueryClassifierService | None = None


def get_query_classifier() -> QueryClassifierService:
    global _classifier
    if _classifier is None:
        _classifier = QueryClassifierService()
    return _classifier
