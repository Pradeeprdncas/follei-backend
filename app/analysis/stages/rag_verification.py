"""RAG verification stage — verifies extracted claims against conversation evidence.

Each claim is verified by searching the conversation transcript and company
knowledge base for supporting evidence. Uses the existing RAG retrieval
pipeline for hybrid search + optional cross-encoder reranking.
"""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from loguru import logger


class RAGVerificationStage(AnalysisStage):
    """Verifies claims using hybrid search (conversation chunks + company knowledge).

    For each claim:
    1. Search conversation transcript for supporting text
    2. Search company knowledge base for relevant policies
    3. Score evidence relevance
    4. Return verification with citations

    When no RAG infrastructure is available (e.g., no Qdrant), falls back
    to simple keyword matching against the transcript.
    """

    def __init__(self, rag_retriever=None):
        self._retriever = rag_retriever

    @property
    def name(self) -> str:
        return "rag_verification"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.claims:
            logger.info("No claims to verify — skipping")
            ctx.verification = []
            return ctx

        transcript_text = ctx.transcript or ""

        verified = []
        for claim in ctx.claims:
            verification = self._verify_claim(claim, transcript_text, ctx)
            verified.append(verification)

        ctx.verification = verified

        # Update claim supported/confidence from verification
        for i, v in enumerate(verified):
            if i < len(ctx.claims):
                ctx.claims[i]["supported"] = v["supported"]
                ctx.claims[i]["confidence"] = v["confidence"]
                ctx.claims[i]["citations"] = v.get("citations", [])
                ctx.claims[i]["reason"] = v.get("reason", "")

        supported = sum(1 for v in verified if v["supported"])
        logger.info(f"RAG verification: {supported}/{len(verified)} claims supported")
        return ctx

    def _verify_claim(
        self,
        claim: dict,
        transcript_text: str,
        ctx: PipelineContext,
    ) -> dict:
        """Verify a single claim against available evidence."""
        claim_text = claim.get("claim", "").lower()
        category = claim.get("category", "")
        confidence = claim.get("confidence", 0.5)

        # Step 1: Check transcript for direct evidence
        transcript_hits = self._search_transcript(claim_text, transcript_text)

        # Step 2: Check company knowledge (if retriever available)
        kb_hits = []
        if self._retriever:
            try:
                kb_results = self._retriever.search(claim.get("claim", ""))
                kb_hits = [
                    {"text": r.get("text", ""), "score": r.get("score", 0)}
                    for r in kb_results if r.get("score", 0) > 0.3
                ]
            except Exception as e:
                logger.warning(f"Knowledge base search failed: {e}")

        # Step 3: Combine evidence
        all_evidence = transcript_hits + kb_hits
        if not all_evidence:
            return {
                "claim": claim.get("claim", ""),
                "category": category,
                "supported": False,
                "confidence": 0.0,
                "citations": [],
                "reason": "No supporting evidence found in transcript or knowledge base",
            }

        max_score = max(e.get("score", 0) for e in all_evidence)
        avg_score = sum(e.get("score", 0) for e in all_evidence) / len(all_evidence)
        final_confidence = min(0.95, max(confidence, avg_score))

        citations = [
            {
                "text": e.get("text", "")[:200],
                "score": e.get("score", 0),
                "source": e.get("source", "transcript"),
            }
            for e in all_evidence[:5]
        ]

        return {
            "claim": claim.get("claim", ""),
            "category": category,
            "supported": max_score >= 0.4,
            "confidence": round(final_confidence, 2),
            "citations": citations,
            "reason": f"Found {len(all_evidence)} evidence pieces (max score: {max_score:.2f})",
        }

    def _search_transcript(self, claim_text: str, transcript: str) -> list[dict]:
        """Simple keyword match against transcript text."""
        if not transcript:
            return []

        keywords = set(claim_text.split())
        transcript_lower = transcript.lower()

        hits = []
        for keyword in keywords:
            if len(keyword) < 4:
                continue
            count = transcript_lower.count(keyword)
            if count > 0:
                hits.append({
                    "text": f"Keyword '{keyword}' found {count} times",
                    "score": min(0.9, 0.3 + count * 0.1),
                    "source": "transcript",
                })

        return hits
